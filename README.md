# Fijazo API

Welcome

API para gestionar apuestas deportivas y llevar un registro personal del historial de apuestas
de cada usuario. MVP centrado en **autenticación de usuarios** y **gestión de apuestas**.

## Tecnologías

- **FastAPI** + **Pydantic v2**
- **MongoDB** (driver async oficial de PyMongo, `AsyncMongoClient`)
- **JWT** (PyJWT) + **bcrypt** para hashing de contraseñas
- **Clean Architecture** + **Repository Pattern**
- **Docker** / **Docker Compose**
- Configuración por variables de entorno (`.env`)

## Arquitectura

```
src/fijazo_api/
├── core/            # config, seguridad (JWT/bcrypt), excepciones de dominio
├── domain/          # entidades e interfaces de repositorio (sin dependencias externas)
│   ├── entities/
│   └── repositories/
├── application/     # casos de uso / servicios (reglas de negocio)
│   └── services/
├── infrastructure/  # implementación MongoDB de los repositorios, conexión, seed
│   ├── database/
│   └── repositories/
├── api/             # capa web: routers, schemas Pydantic, dependencias (DI)
│   ├── routers/
│   └── schemas/
└── main.py          # app factory, lifespan, manejo global de excepciones
```

Las dependencias apuntan siempre hacia el dominio. Para añadir en el futuro **estadísticas,
rankings o análisis de rendimiento** basta con crear nuevos casos de uso y, si hace falta, nuevos
repositorios, sin modificar el núcleo (dominio) ni la infraestructura base.

## Puesta en marcha con Docker Compose (recomendado)

```bash
cp .env.example .env      # ajusta JWT_SECRET y credenciales de admin
docker compose up --build
```

- API: http://localhost:8000
- Documentación Swagger: http://localhost:8000/docs
- MongoDB expuesto en `localhost:27017`

Al arrancar se crean los índices únicos y se siembra el usuario **ADMIN** definido en `.env`.

## Ejecución local (sin Docker)

Requiere Python 3.14+, Poetry y una instancia de MongoDB en `localhost:27017`.

```bash
poetry install
cp .env.example .env
poetry run uvicorn fijazo_api.main:app --reload
```

> La configuración se lee de `.env` (no de `.env.local`). Si no existe, `MONGO_URI` cae al
> valor por defecto `mongodb://localhost:27017`.

## Despliegue en Vercel

La API se despliega como una única Vercel Function con el runtime de Python.

| Archivo | Papel |
|---|---|
| `api/index.py` | Entrypoint: reexporta `app`. Añade `src/` al path por si el instalador no instala el paquete. |
| `vercel.json` | `maxDuration` de la función y exclusión de tests/Docker del bundle. |
| `.python-version` | Fija Python 3.14 (Vercel soporta 3.12, 3.13 y 3.14). |
| `pyproject.toml` | Vercel resuelve estas dependencias con uv; `requirements.txt` no hace falta. |

### 1. Variables de entorno (Project Settings → Environment Variables)

| Variable | Valor | Nota |
|---|---|---|
| `MONGO_URI` | Cadena SRV de Atlas | **Secreto**. No la subas al repo. |
| `MONGO_DB_NAME` | `fijazo` | |
| `JWT_SECRET` | `openssl rand -hex 32` | **Secreto**. No dejes el valor por defecto. |
| `CORS_ORIGINS` | `https://<frontend>.vercel.app` | Sin esto el navegador bloquea el frontend. |
| `CORS_ORIGIN_REGEX` | `^https://<proyecto>-.*\.vercel\.app$` | Opcional: habilita los preview deployments. |
| `RUN_STARTUP_BACKFILL` | `false` | **Obligatorio en Vercel**: cada cold start recorrería todos los usuarios. |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | credenciales del admin | El email debe ser de un dominio real (`.local` lo rechaza `EmailStr`). |
| `MONGO_MAX_POOL_SIZE` | `10` | Conexiones por instancia; el total contra Atlas es instancias × este valor. |

### 2. MongoDB Atlas

Las funciones de Vercel no tienen IP fija, así que en **Network Access** hay que permitir
`0.0.0.0/0` y apoyarse en usuario/contraseña de la cadena de conexión.

### 3. Desplegar

```bash
vercel            # preview
vercel --prod     # producción
```

Comprueba `https://<api>.vercel.app/health` → `{"status":"ok"}`. Swagger queda en `/docs`.

### Notas de serverless

- El lifespan de FastAPI **sí** se ejecuta en Vercel, una vez por cold start: abre la conexión
  a Mongo, crea los índices (idempotente) y siembra el admin. El backfill se desactiva con
  `RUN_STARTUP_BACKFILL=false`; las estadísticas se recalculan igualmente por usuario en cada
  endpoint.
- Vercel no lee `poetry.lock`: resuelve las dependencias de `pyproject.toml` en cada build
  dentro de los rangos declarados. Para builds reproducibles, commitea un `uv.lock`.

## Endpoints

### Autenticación
| Método | Ruta             | Descripción                          |
|--------|------------------|--------------------------------------|
| POST   | `/auth/register` | Registro de usuario                  |
| POST   | `/auth/login`    | Login, devuelve un token JWT         |
| GET    | `/users/me`      | Perfil del usuario autenticado       |

### Apuestas (requieren `Authorization: Bearer <token>`)
| Método | Ruta          | Descripción                                        |
|--------|---------------|----------------------------------------------------|
| POST   | `/bets`       | Crear una apuesta (simple o parlay)                |
| GET    | `/bets`       | Listar apuestas propias (paginación + filtros)     |
| GET    | `/bets/{id}`  | Consultar una apuesta por ID                       |
| PUT    | `/bets/{id}`  | Editar una apuesta                                 |
| DELETE | `/bets/{id}`  | Eliminar una apuesta                               |

Filtros de `GET /bets`: `page`, `page_size`, `status`, `sport`, `bet_type`.

**Simple vs Parlay**: una apuesta simple usa solo la selección principal. Un **parlay** añade
selecciones extra en `legs` (`bet_type=PARLAY` requiere ≥1 leg; SIMPLE debe ir sin legs). La
**cuota combinada** (`combined_odds`) es el producto de todas las cuotas y sobre ella se calculan el
retorno/beneficio potencial. En el Excel, las filas que comparten la columna **`Ticket`** forman un
parlay (1ª fila = ticket + selección principal; siguientes = legs).

### Administración de usuarios (solo ADMIN)
| Método | Ruta                    | Descripción                              |
|--------|-------------------------|------------------------------------------|
| GET    | `/users`                | Listar usuarios (paginado)               |
| GET    | `/users/{id}`           | Detalle de un usuario                    |
| PATCH  | `/users/{id}/active`    | Activar/desactivar un usuario            |

Un usuario **desactivado** no puede iniciar sesión ni usar su token (403). Un administrador no puede
desactivarse a sí mismo.

### Importación masiva desde Excel (requiere token)
| Método | Ruta             | Descripción                                          |
|--------|------------------|------------------------------------------------------|
| GET    | `/bets/template` | Descarga la plantilla `.xlsx` para importar apuestas |
| POST   | `/bets/import`   | Sube un `.xlsx` y procesa la importación             |

La plantilla trae los encabezados formateados y **listas desplegables** para *Estado* y *Tipo de
apuesta*. Columnas (en este orden): `Deporte, Liga, Evento, Tipo de apuesta, Mercado, Selección,
Cuota, Stake, Casa de apuestas, Fecha y hora del evento, Estado, Notas, ID de referencia`
(esta última opcional). Valores válidos: **Tipo** `SIMPLE`/`PARLAY`, **Estado**
`PENDING`/`WON`/`LOST`/`VOID`.

Cada fila se valida con **las mismas reglas** que la creación individual (`cuota > 1`, `stake > 0`,
campos obligatorios, enums). Una fila con errores se rechaza **sin detener** las demás. La respuesta
resume `total_rows`, `imported`, `rejected` y una lista de `errors` con `row`, `field` y `error`.
Se detectan duplicados dentro del archivo (evento+selección+fecha), `reference_id` repetido en el
archivo y `reference_id` ya existente del usuario. Las apuestas importadas **actualizan
automáticamente las estadísticas y el ranking**.

### Estadísticas y ranking (requieren token)
| Método | Ruta              | Descripción                                       |
|--------|-------------------|---------------------------------------------------|
| GET    | `/statistics/me`  | Estadísticas del usuario autenticado              |
| GET    | `/ranking`        | Ranking global paginado (orden por `ranking_score`) |
| GET    | `/ranking/top`    | Top de usuarios (`limit`, por defecto 10)         |
| GET    | `/ranking/me`     | Posición del usuario en el ranking                |

Las estadísticas **no se almacenan a mano**: se calculan a partir del historial de apuestas y se
**materializan** en la colección `user_statistics`, que se **recalcula automáticamente** en cada
creación, edición o borrado de apuestas (y se rellena en el arranque para las apuestas existentes).

### Rangos y logros (gamificación, requieren token)
| Método | Ruta                | Descripción                                          |
|--------|---------------------|------------------------------------------------------|
| GET    | `/achievements`     | Catálogo completo de logros                          |
| GET    | `/achievements/me`  | Logros del usuario (desbloqueados + pendientes)      |
| GET    | `/ranks`            | Todos los rangos disponibles                         |
| GET    | `/ranks/me`         | Rango actual, puntuación y progreso al siguiente     |

El rango se calcula con una **puntuación modular** ([rank_scorer.py](src/fijazo_api/domain/services/rank_scorer.py))
que combina win rate, ROI, beneficio, consistencia, racha, volumen y **antigüedad** en la
plataforma, con penalización por muestra pequeña. Los 9 rangos (Novato…Leyenda) y sus umbrales son
**configurables** en [ranks_config.py](src/fijazo_api/domain/services/ranks_config.py).

Los **logros** están definidos en un catálogo extensible
([achievements_catalog.py](src/fijazo_api/domain/services/achievements_catalog.py)) por categorías
(rachas, experiencia, rentabilidad, precisión, actividad, casas, deportes). Añadir un logro nuevo es
solo registrar otra entrada; el evaluador no cambia. Se **evalúan automáticamente** en cada cambio de
apuestas —solo los aún bloqueados, sin duplicar— y se persisten con su fecha en `user_progression`.
Reutilizan las estadísticas ya calculadas (rango y logros nunca se editan a mano).

### Campos calculados de una apuesta
- `potential_return = stake × odds`
- `potential_profit = stake × (odds − 1)`
- `implied_probability = 1 / odds`
- `created_at`, `updated_at`

### Fórmulas de estadísticas
Conjuntos: **finalizadas** = WON+LOST+VOID · **decididas** = WON+LOST (VOID es *push*, se excluye
del win rate, rachas y consistencia). Resultado realizado por apuesta: WON → `stake·(odds−1)`;
LOST → `−stake`; VOID → `0` (se devuelve el stake).

- **Win Rate** = ganadas / decididas · 100
- **ROI** = beneficio neto / stake total · 100
- **Beneficio neto** = retorno total − stake total
- **Racha actual** = W/L consecutivas al final (ordenado por `event_datetime`, saltando VOID);
  positiva = victorias, negativa = derrotas. **Mejor racha** = mayor racha de victorias
- **Consistencia** = `100 / (1 + stddev(roi_i))`, con `roi_i` = beneficio/stake por apuesta decidida

### `ranking_score`
Puntuación compuesta (0..100) de componentes normalizados —win rate, ROI, beneficio (acotado con
`tanh`), consistencia, racha y volumen— con pesos ajustables en
[`ranking_scorer.py`](src/fijazo_api/domain/services/ranking_scorer.py). Incluye una **penalización
por muestra pequeña**: `confidence = min(1, finalizadas / 30)`, de modo que un usuario con pocas
apuestas no escala a los primeros puestos. Todas las constantes (umbral, pesos, escalas) están
centralizadas y documentadas para ajustar o añadir métricas sin tocar la orquestación.

## Reglas de validación

- Usuario: 3–15 caracteres · Contraseña: 8–64 caracteres.
- Email y username únicos (validado en servicio + índice único en MongoDB).
- Cuota (`odds`) > 1 · Stake > 0 · Campos obligatorios no vacíos.
- Cada apuesta pertenece únicamente al usuario autenticado.

## Tests

Los tests de integración requieren una instancia de MongoDB accesible (por defecto
`mongodb://localhost:27017`, configurable con `TEST_MONGO_URI`). Usan una base de datos separada
(`fijazo_test`) que se limpia entre pruebas.

```bash
# Con el mongo de docker-compose levantado, o un mongo local:
poetry run pytest
```
# fijazoo-api
