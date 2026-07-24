import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { Transport } from '@nestjs/microservices';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, transform: true }),
  );

  // Segundo transporte además del HTTP: TCP para el contrato `users.validate`,
  // consumible por otros servicios sin pasar por el gateway.
  app.connectMicroservice({
    transport: Transport.TCP,
    options: {
      host: process.env.TCP_HOST ?? '0.0.0.0',
      port: parseInt(process.env.TCP_PORT ?? '3011', 10),
    },
  });

  await app.startAllMicroservices();

  const port = parseInt(process.env.HTTP_PORT ?? '3001', 10);
  await app.listen(port, '0.0.0.0');
}
void bootstrap();
