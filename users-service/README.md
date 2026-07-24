# users-service

Servicio NestJS autónomo dueño del dominio de usuarios de Fijazo. Migra el modelo
`User` y los endpoints de administración del monolito, contra su **propia base de datos**.

## Endpoints HTTP

| Método | Ruta                | Descripción                          |
| ------ | ------------------- | ------------------------------------ |
| POST   | `/users`            | Crea un usuario (password hasheado)  |
| GET    | `/users`            | Lista paginada (`page`, `page_size`) |
| GET    | `/users/:id`        | Obtiene un usuario por id            |
| PATCH  | `/users/:id/active` | Activa/desactiva un usuario          |
| PATCH  | `/users/:id/role`   | Cambia el rol (`USER`/`ADMIN`)       |
| GET    | `/health`           | Healthcheck                          |

La respuesta de usuario es equivalente a la del monolito: `id`, `username`, `email`,
`role`, `active`, `created_at` (sin contraseña). La lista devuelve
`{ items, total, page, page_size }`.

## Puesta en marcha

```bash
cp .env.example .env
npm install
npm run start:dev
```

Requiere una instancia de MongoDB (por defecto `mongodb://localhost:27017`, base
`users_service`).

## Tests

```bash
npm test        # e2e con mongodb-memory-server, sin Mongo externo
```
