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

const TCP_PORT = 3099;

/**
 * Prueba del contrato TCP `users.validate`: un `user_id` válido devuelve el
 * `{ active, tier }` correcto, verificado con un cliente TCP real.
 */
describe('users.validate (TCP e2e)', () => {
  let app: INestApplication;
  let mongod: MongoMemoryServer;
  let client: ClientProxy;

  beforeAll(async () => {
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
  });

  const validate = (user_id: string) =>
    firstValueFrom(client.send('users.validate', { user_id }));

  it('devuelve active y tier para un user_id válido', async () => {
    const created = await request(app.getHttpServer())
      .post('/users')
      .send({ username: 'tcp', email: 'tcp@fijazo.com', password: 'secret123' })
      .expect(201);

    const res = await validate(created.body.id);
    expect(res).toEqual({ active: true, tier: 'standard' });
  });

  it('refleja la desactivación en el contrato TCP', async () => {
    const created = await request(app.getHttpServer())
      .post('/users')
      .send({ username: 'off', email: 'off@fijazo.com', password: 'secret123' })
      .expect(201);
    await request(app.getHttpServer())
      .patch(`/users/${created.body.id}/active`)
      .send({ active: false })
      .expect(200);

    const res = await validate(created.body.id);
    expect(res).toEqual({ active: false, tier: 'standard' });
  });

  it('trata un user_id inexistente como no activo', async () => {
    const res = await validate('000000000000000000000000');
    expect(res).toEqual({ active: false, tier: null });
  });
});
