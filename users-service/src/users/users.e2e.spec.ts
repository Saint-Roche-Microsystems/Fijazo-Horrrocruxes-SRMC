import { INestApplication, ValidationPipe } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { MongooseModule } from '@nestjs/mongoose';
import { MongoMemoryServer } from 'mongodb-memory-server';
import request from 'supertest';
import { UsersModule } from './users.module';

/**
 * Prueba end-to-end del CRUD/administración contra una Mongo en memoria: verifica
 * que los endpoints responden equivalentemente a como lo hacían en el monolito.
 */
describe('Users CRUD (e2e)', () => {
  let app: INestApplication;
  let mongod: MongoMemoryServer;

  beforeAll(async () => {
    mongod = await MongoMemoryServer.create();
    const moduleRef = await Test.createTestingModule({
      imports: [MongooseModule.forRoot(mongod.getUri()), UsersModule],
    }).compile();
    app = moduleRef.createNestApplication();
    app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
    await app.init();
  });

  afterAll(async () => {
    await app.close();
    await mongod.stop();
  });

  const server = () => app.getHttpServer();

  it('crea, obtiene, lista, desactiva y cambia el rol de un usuario', async () => {
    // Crear
    const created = await request(server())
      .post('/users')
      .send({ username: 'ana', email: 'ana@fijazo.com', password: 'secret123' })
      .expect(201);
    expect(created.body).toMatchObject({
      username: 'ana',
      email: 'ana@fijazo.com',
      role: 'USER',
      active: true,
    });
    expect(created.body.id).toBeDefined();
    expect(created.body.hashed_password).toBeUndefined();
    const id = created.body.id;

    // Obtener por id
    const fetched = await request(server()).get(`/users/${id}`).expect(200);
    expect(fetched.body.username).toBe('ana');

    // Listar paginado
    const listed = await request(server())
      .get('/users?page=1&page_size=10')
      .expect(200);
    expect(listed.body.total).toBe(1);
    expect(listed.body.items).toHaveLength(1);
    expect(listed.body.page).toBe(1);
    expect(listed.body.page_size).toBe(10);

    // Desactivar
    const deactivated = await request(server())
      .patch(`/users/${id}/active`)
      .send({ active: false })
      .expect(200);
    expect(deactivated.body.active).toBe(false);

    // Cambiar rol
    const promoted = await request(server())
      .patch(`/users/${id}/role`)
      .send({ role: 'ADMIN' })
      .expect(200);
    expect(promoted.body.role).toBe('ADMIN');
  });

  it('rechaza username/email duplicado con 409', async () => {
    await request(server())
      .post('/users')
      .send({ username: 'bob', email: 'bob@fijazo.com', password: 'secret123' })
      .expect(201);
    await request(server())
      .post('/users')
      .send({ username: 'bob', email: 'bob@fijazo.com', password: 'secret123' })
      .expect(409);
  });

  it('devuelve 404 para un id inexistente', async () => {
    await request(server()).get('/users/000000000000000000000000').expect(404);
  });
});
