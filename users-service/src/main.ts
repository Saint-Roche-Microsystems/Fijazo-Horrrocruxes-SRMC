import { NestFactory } from '@nestjs/core';
import { ValidationPipe } from '@nestjs/common';
import { AppModule } from './app.module';

async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, transform: true }),
  );
  const port = parseInt(process.env.HTTP_PORT ?? '3001', 10);
  await app.listen(port, '0.0.0.0');
}
void bootstrap();
