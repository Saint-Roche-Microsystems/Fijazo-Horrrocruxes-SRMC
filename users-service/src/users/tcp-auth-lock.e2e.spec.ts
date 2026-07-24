import * as http from 'http';
import { AddressInfo } from 'net';
import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { MongooseModule } from '@nestjs/mongoose';
import {
  ClientProxy,
  ClientProxyFactory,
  Transport,
} from '@nestjs/microservices';
import { MongoMemoryServer } from 'mongodb-memory-server';
import { firstValueFrom } from 'rxjs';
import request from 'supertest';
import { UsersModule } from './users.module';

const TCP_PORT = 3098;
const INTERNAL_KEY = 'test-internal-key';

/**
 * Verifica el hop B->C: una cuenta bloqueada en auth-service se refleja en la
 * respuesta TCP de users.validate, y la llamada saliente lleva `X-Internal-Key`.
 * auth-service se sustituye por un stub HTTP.
 */
describe('users.validate hop B->C (TCP + auth stub)', () => {
  let app: INestApplication;
  let mongod: MongoMemoryServer;
  let client: ClientProxy;
  let authStub: http.Server;
  let lockedUntil: string;
  let receivedKey: string | undefined;

  beforeAll(async () => {
    // Stub de auth-service: /internal/lock-status/:id, marca bloqueada a "lockeduser".
    authStub = http.createServer((req, res) => {
      receivedKey = req.headers['x-internal-key'] as string | undefined;
      const id = (req.url ?? '').split('/').pop() ?? '';
      const locked = id === LOCKED_ID;
      res.setHeader('content-type', 'application/json');
      res.end(
        JSON.stringify({
          user_id: id,
          locked,
          locked_until: locked ? lockedUntil : null,
          retry_after_seconds: locked ? 300 : 0,
          failed_login_attempts: locked ? 5 : 0,
          active: true,
        }),
      );
    });
    await new Promise<void>((r) => authStub.listen(0, r));
    const authPort = (authStub.address() as AddressInfo).port;

    process.env.AUTH_SERVICE_URL = `http://127.0.0.1:${authPort}`;
    process.env.INTERNAL_API_KEY = INTERNAL_KEY;

    mongod = await MongoMemoryServer.create();
    const moduleRef = await Test.createTestingModule({
      imports: [MongooseModule.forRoot(mongod.getUri()), UsersModule],
    }).compile();
    app = moduleRef.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    app.connectMicroservice({
      transport: Transport.TCP,
      options: { host: '127.0.0.1', port: TCP_PORT },
    });
    await app.startAllMicroservices();
    await app.init();

    client = ClientProxyFactory.create({
      transport: Transport.TCP,
      options: { host: '127.0.0.1', port: TCP_PORT },
    });
    await client.connect();
  });

  afterAll(async () => {
    await client.close();
    await app.close();
    await mongod.stop();
    await new Promise<void>((r) => authStub.close(() => r()));
  });

  const validate = (user_id: string) =>
    firstValueFrom(client.send('users.validate', { user_id })) as Promise<{
      active: boolean;
      tier: string | null;
      locked: boolean;
      locked_until: string | null;
    }>;

  // Se rellena tras crear el usuario "bloqueado".
  let LOCKED_ID = '';

  it('refleja una cuenta bloqueada y envía X-Internal-Key', async () => {
    lockedUntil = new Date(Date.now() + 300_000).toISOString();
    const created = await request(app.getHttpServer())
      .post('/users')
      .send({ username: 'locked', email: 'locked@fijazo.com', password: 'secret123' })
      .expect(201);
    LOCKED_ID = created.body.id;

    const res = await validate(LOCKED_ID);
    expect(res.active).toBe(true);
    expect(res.tier).toBe('standard');
    expect(res.locked).toBe(true);
    expect(res.locked_until).toBe(lockedUntil);
    expect(receivedKey).toBe(INTERNAL_KEY);
  });

  it('una cuenta no bloqueada devuelve locked=false', async () => {
    const created = await request(app.getHttpServer())
      .post('/users')
      .send({ username: 'okuser', email: 'ok@fijazo.com', password: 'secret123' })
      .expect(201);

    const res = await validate(created.body.id);
    expect(res.locked).toBe(false);
    expect(res.locked_until).toBeNull();
  });
});
