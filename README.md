# Fijazo API

![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white)
![NestJS](https://img.shields.io/badge/NestJS-E0234E?style=flat&logo=nestjs&logoColor=white)
![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white)
![MongoDB](https://img.shields.io/badge/MongoDB-47A248?style=flat&logo=mongodb&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white)
![RabbitMQ](https://img.shields.io/badge/RabbitMQ-FF6600?style=flat&logo=rabbitmq&logoColor=white)
![JWT](https://img.shields.io/badge/JWT-000000?style=flat&logo=jsonwebtokens&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white)

API para gestionar apuestas deportivas y llevar un registro personal del historial de apuestas
de cada usuario. MVP de arquitectura de microservicios centrado en **autenticación de usuarios** y **gestión de apuestas**.

## Equipo
| Integrante | Rol | GitHub |
|---|---|---|
| Carlos Hernández | Backend & Arquitectura | @gomiiDev |
| Olivier Paspuel | Transportes TCP & RabbitMQ | @vieerr |
| Antonio Revilla | Seguridad & Observabilidad | @RevillaA |
| Frederick Tipán | Documentación & Integración | @devdiagon |

## Descripción del MVP
El sistema gestiona apuestas deportivas y el progreso/historial de cada usuario, migrado desde un monolito hacia una arquitectura de microservicios independientes por dominio. Cada servicio es dueño de su propia base de datos y se comunica con los demás vía transporte síncrono (HTTP/TCP) para consistencia inmediata, y asíncrono (Redis Streams/RabbitMQ) para eventos que no deben bloquear al usuario.
- **auth-service (FastAPI):** credenciales, login/registro, emisión de JWT, bloqueo de cuenta por intentos fallidos, auditoría de seguridad.
- **users-service (NestJS):** dominio de usuarios (perfil, roles, activación/desactivación), expone validación de usuario por TCP para bets-service.
- **bets-service (FastAPI):** apuestas simples y parlays (CRUD), cálculo de cuotas combinadas/retorno potencial, import/export Excel.
- **progression-service (FastAPI):** estadísticas, rachas, logros y ranking derivados de las apuestas de cada usuario.
- **API Gateway (NestJS):** punto único de entrada, valida JWT y hace proxy por prefijo de ruta hacia cada microservicio.

## Stack
- **Framework:** FastAPI (auth, bets, progression) · NestJS (api-gateway, users)
- **Síncrono:** TCP (bets-service → users-service) y HTTP (gateway → servicios, users-service → auth-service) · **Eventos:** Redis Streams (auth-service>`security-events`) · **2.º transporte:** RabbitMQ (exchange>`bets.events` → cola `progression.recalc`) · **Contrato:** Schemas compartidos.
- **Seguridad:** JWT (PyJWT) + `JwtAuthGuard`/`RolesGuard` en el gateway · **Observabilidad:** Sentry
- **BD:** MongoDB (una base por servicio) · **Contenedores:** Docker Compose · **Estructura:** repo maestro con submódulos git por microservicio

## Cómo ejecutar

### Preparación

```bash
node scripts/bootstrap.mjs
```

Verifica que se encuentren las dependencias necesarias: `node`, `npm` y `poetry`, sincroniza los submódulos si falta alguno y genera el `.env` de cada microservicio. Finalmente instala las dependencias de cada microservicio.

### Para producción

```bash
docker compose up --build -d
```

Levanta todo el sistema, contenerizadas en imagenes de docker con el único puerto público: `3000` (api-gateway).

### Ejecutar en desarrollo

```bash
node scripts/local_run.mjs
```

Imprime, servicio por servicio, la secuencia exacta para levantarlo a mano en su propia terminal.

## Arquitectura

![Arquitectura del sistema](docs/architecture.png)

## Metodología
- **Kanban:** [GitHub Projects del equipo](https://github.com/orgs/Saint-Roche-Microsystems/projects/1/views/1)

![Tablero Kanban](docs/kanban.png)
- **Ramificación:** GitHub Flow — `main` protegida, ramas `feat/…`/`fix/…`, PRs revisados, tags por avance.
- **Commits semánticos:** Conventional Commits.

## Patrones y principios aplicados
- **API Gateway / Proxy:** el gateway centraliza autenticación y enruta por prefijo hacia cada microservicio (patrón propio sobre NestJS).
- **Publisher/Subscriber:** bets-service publica eventos de dominio a RabbitMQ; auth-service publica eventos de seguridad a Redis Streams.
- **Repository Pattern:** acceso a MongoDB encapsulado por repositorio en los servicios FastAPI.
- **DIP / Guards:** `JwtAuthGuard` y `RolesGuard` de Nest para autorización declarativa (`@Public()`, `@Roles()`).
- **Fail-open en eventos:** la publicación a Redis no bloquea el login si Redis falla (resiliencia sobre disponibilidad estricta).

---

## 🟢 Avance 1 — Acoplamiento temporal y latencia · `tag v1-avance1`
### Caminos
- **Síncrono (TCP):** Gateway → **bets-service** → **users-service** (`users.validate`, cliente TCP contra el transporte `Transport.TCP` de Nest).
- **Asíncrono (Redis):** auth-service publica el evento de seguridad en el stream `security-events` (`XADD`); users-service lo consume con un consumer group (`XREADGROUP`) y marca `security_locked` en el perfil, sin bloquear al usuario que originó el evento.

### Acoplamiento temporal
Al apagar **users-service**, cualquier `POST /bets` que dependa de `users.validate` falla de inmediato: `bets-service` abre una conexión TCP nueva por cada validación (sin capa de reconexión), por lo que el `ConnectionRefusedError` se propaga como `UserValidationUnavailableError` → **503** en la respuesta HTTP.

![Error 503 al caer users-service, servicio bets-service sigue vivo](docs/tcp_request_error.png)

En la captura: el panel izquierdo confirma que `users-service` está caido, pero el `POST /bets` responde `503 Service Unavailable` con el detalle `"No se pudo validar el usuario contra users-service: ... Connect call failed ('127.0.0.1', 3011)"` — el fallo del vecino síncrono se refleja íntegramente en la respuesta al cliente.

El flujo asíncrono, en cambio, no depende de que el consumidor esté disponible en el instante de la publicación: el stream de Redis retiene el evento y `users-service` lo procesa al reactivarse, sin que el login que lo originó se haya visto afectado.

### Análisis
En el camino síncrono (TCP), la latencia total de la petición es la **suma** de los tiempos de cada salto: Gateway → bets-service → (TCP) users-service, y cada eslabón depende de que el anterior responda dentro de su timeout para poder continuar. Si un eslabón cae, el error se propaga hacia arriba y el cliente lo recibe en la misma petición (fail-closed): esto es **acoplamiento temporal** — el productor (bets-service) y el consumidor (users-service) deben estar activos **al mismo tiempo** para que la operación se complete. En el camino asíncrono (Redis Streams), auth-service y users-service no comparten ventana temporal: el productor persiste el evento y sigue, el consumidor lo procesa cuando puede, desacoplando la disponibilidad de ambos servicios del éxito de la operación original.

---

## 🟡 Avance 2 — Comunicación: HTTP/REST interno + 2.º transporte + excepciones · `tag v2-avance2`
### HTTP/REST interno (contrato)
**users-service → auth-service**: `GET /internal/lock-status/{user_id}`, disparado dentro del propio hop TCP `users.validate` (bets-service → users-service), como paso B→C de la cadena de validación de una apuesta. auth-service devuelve `{locked, locked_until, retry_after_seconds, failed_login_attempts, active}`. El contrato exige el secreto de servicio compartido `X-Internal-Key`: sin él (o con uno incorrecto) el router `/internal/*` de auth-service responde `401 Unauthorized` con `"Secreto de servicio inválido o ausente."`, aplicado a nivel de router para que ninguna ruta interna futura pueda olvidarse de la protección.

![Control de acceso al endpoint interno vía X-Internal-Key](docs/avances2/internal_http_api_secret.png)

En la captura: la misma petición `GET /internal/lock-status/{id}` sin la cabecera `X-Internal-Key` responde `401`; con la cabecera correcta responde `200` con el estado real de bloqueo — el contrato exige el secreto en toda la superficie `/internal/*`, no solo en rutas puntuales.

El mismo `X-Request-Id` originado en la petición del gateway se propaga por las 4 patas de la cadena (gateway → TCP → HTTP interno → evento Redis/RabbitMQ), lo que permite correlacionar en logs una misma operación de negocio a través de procesos distintos:

![Trazabilidad de X-Request-Id entre users-service y auth-service](docs/avances2/internal_http_api_traceability.png)

### Segundo transporte
Transporte elegido: **RabbitMQ** (exchange topic `bets.events`, cola `progression.recalc` con binding `bet.#`). Flujo tipo **queue con enrutado por topic**: cada mutación de apuesta (`bet.created`/`bet.updated`/`bet.deleted`) se publica en `bets-service` con routing key igual al tipo de evento, ya persistida la apuesta en Mongo — el evento es un anuncio de un hecho ya ocurrido, no parte de la transacción.

![Publicación en el exchange bets.events y respuesta 201 al cliente](docs/avances2/bet_message.png)

![Mensaje encolado en progression.recalc, listo para consumirse](docs/avances2/progression_consumer.png)

En la captura del exchange se ve el pico de tasa de mensajes en el momento del `POST /bets`, y el mensaje ya en la cola `progression.recalc` (`Ready: 3`, sin consumidores activos) — evidencia de que la publicación funciona de forma independiente de si hay o no un consumidor levantado del otro lado.

### Comparación de transportes
| Transporte | Tipo | Patrón | Uso en el proyecto |
|---|---|---|---|
| TCP | Síncrono | Petición-respuesta | `bets-service` → `users-service` (`users.validate`), valida al usuario antes de crear/actualizar una apuesta. |
| Redis | Asíncrono | PUB/SUB (Streams + consumer group) | `auth-service` → `users-service`, eventos de seguridad (`user.login_failed`/`user.locked`) que marcan `security_locked` en el perfil sin bloquear el login. |
| RabbitMQ | Asíncrono | Queue con enrutado por topic (exchange `bets.events` → cola `progression.recalc`) | `bets-service` anuncia mutaciones de apuesta para que `progression-service` recalcule estadísticas/rachas/logros. |
| HTTP/REST | Síncrono | Contrato/RPC | `api-gateway` → todos los servicios (proxy); `users-service` → `auth-service` (`/internal/lock-status/{id}`), consulta de estado de bloqueo dentro del hop TCP. |

TCP y HTTP/REST síncronos se usan cuando la respuesta debe reflejar el estado real **en el instante** de la petición (validar un usuario, consultar si está bloqueado antes de aceptar una apuesta): el costo es acoplamiento temporal y latencia acumulada, pero se gana consistencia inmediata. Redis Streams y RabbitMQ se usan cuando la acción disparadora no debe esperar a que el interesado la procese (notificar un bloqueo de cuenta, avisar que hay que recalcular progreso): se gana desacoplamiento y resiliencia ante caídas temporales del consumidor, a cambio de consistencia eventual.

### Manejo de excepciones
Se identificaron y evidenciaron dos mecanismos de control de errores con criterios opuestos, ambos con `try/except` que evitan que un fallo de infraestructura tumbe el servicio:

- **Fail-closed (TCP bets→users, ver Avance 1)**: `TcpUserValidator.validate()` captura `(asyncio.TimeoutError, OSError, ValueError)` y los traduce a `UserValidationUnavailableError` → **503** explícito en la respuesta HTTP. El error se comunica al cliente, no se oculta.
- **Fail-open (RabbitMQ, `BetService._publish`)**: la publicación del evento de dominio ocurre **después** de persistir la apuesta en Mongo, envuelta en `try/except Exception` que solo hace `logger.exception(...)`, sin revertir ni propagar. Para evidenciarlo sin apagar el contenedor completo de RabbitMQ (lo que activa la reconexión automática de `aio_pika.connect_robust` y oculta el error a nivel de aplicación), se forzó un error de protocolo eliminando el exchange `bets.events` en caliente:

![Excepción controlada: 201 Created al cliente pese al fallo de publicación](docs/avances2/controlled_error_rabbitmq.png)

En la captura: el `POST /bets` sigue respondiendo `201 Created` con la apuesta persistida, mientras el log estructurado de `bets-service` registra `"No se pudo publicar el evento de dominio 'bet.created'."` (`exc_type: ChannelNotFoundEntity`) — el fallo del segundo transporte no afecta la respuesta al usuario ni la integridad del dato ya guardado, que es la fuente de verdad.

Mismo patrón fail-open aplica en `RedisSecurityEventPublisher.publish()` (auth-service) y en `AuthClient.getLockStatus()` (users-service → auth-service): ambos asumen el valor "seguro por defecto" (`locked: false`) ante un fallo de su dependencia, priorizando disponibilidad del login sobre bloqueo estricto — inconsistente con el criterio fail-closed que aplica bets-service en el mismo tipo de dependencia, documentado como gap pendiente de definición de criterio único.

---