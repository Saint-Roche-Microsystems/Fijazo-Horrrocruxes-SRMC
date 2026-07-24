"""Punto de entrada de la aplicación FastAPI (app factory)."""

import logging
from contextlib import asynccontextmanager

import aio_pika
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from fijazo_api.api.routers import (
    achievements,
    auth,
    bets,
    ranking,
    ranks,
    statistics,
    users,
)
from fijazo_api.core.config import get_settings
from fijazo_api.core.exceptions import (
    AccountLockedError,
    AlreadyExistsError,
    DomainError,
    ForbiddenError,
    InvalidCredentialsError,
    NotFoundError,
)
from fijazo_api.core.logging import Timer, new_request_id, set_request_id, setup_logging
from fijazo_api.infrastructure.database.mongo import (
    create_client,
    ensure_indexes,
    get_database,
)
from fijazo_api.infrastructure.repositories.mongo_user_repository import (
    MongoUserRepository,
)
from fijazo_api.infrastructure.seed import seed_admin

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestiona la conexión a MongoDB, índices y seed durante el ciclo de vida."""

    settings = get_settings()
    client = create_client(
        settings.mongo_uri,
        max_pool_size=settings.mongo_max_pool_size,
        server_selection_timeout_ms=settings.mongo_server_selection_timeout_ms,
    )
    db = get_database(client, settings.mongo_db_name)

    app.state.mongo_client = client
    app.state.db = db

    user_repo = MongoUserRepository(db)
    await ensure_indexes(db)
    await seed_admin(user_repo, settings)

    # El arranque ya no ejecuta ningún recálculo masivo (T-029): esa lógica vive en
    # scripts/backfill_progression.py, un job manual que publica un evento histórico por
    # usuario hacia bets.events y reutiliza el consumer de progression-service (T-026).

    # Publisher de eventos (T-028): sin URL configurada, sigue con el publisher de log de
    # desarrollo (ver deps.get_event_publisher). BetService ya no llama a ProgressionService
    # directamente; la progresión se actualiza sólo al consumir este exchange (T-026).
    rabbit_connection = None
    if settings.rabbitmq_url:
        rabbit_connection = await aio_pika.connect_robust(settings.rabbitmq_url)
        channel = await rabbit_connection.channel()
        app.state.bets_events_exchange = await channel.get_exchange(
            settings.bets_events_exchange
        )
    else:
        app.state.bets_events_exchange = None

    try:
        yield
    finally:
        if rabbit_connection is not None:
            await rabbit_connection.close()
        await client.close()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log estructurado (JSON) de cada petición REST: método, ruta, status y duración.

    Es el punto único de log de peticiones: el access log por defecto de uvicorn se
    desactiva en :func:`setup_logging` para no duplicar cada línea. También propaga
    un ``request_id`` (nuevo o heredado de ``X-Request-ID``) que aparece en todos los
    logs generados durante la petición, incluidas las excepciones.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or new_request_id()
        set_request_id(request_id)
        timer = Timer()

        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "Excepción no controlada procesando petición",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else None,
                    "duration_ms": timer.elapsed_ms(),
                },
            )
            raise

        logger.info(
            "Petición procesada",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": timer.elapsed_ms(),
                "client_ip": request.client.host if request.client else None,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Rechaza con 413 peticiones cuyo ``Content-Length`` supere el límite configurado.

    Se comprueba por cabecera antes de leer el body: evita bufferizar payloads
    enormes en memoria (p. ej. subidas de plantillas .xlsx maliciosamente grandes).
    """

    def __init__(self, app, max_body_bytes: int) -> None:
        super().__init__(app)
        self._max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self._max_body_bytes:
                    return JSONResponse(
                        status_code=413,
                        content={"detail": "Cuerpo de la petición demasiado grande."},
                    )
            except ValueError:
                pass
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Añade cabeceras de hardening y quita ``Server`` (revela uvicorn/versión)."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Uvicorn añade su propio "Server: uvicorn" al final si la cabecera no está
        # presente en la respuesta; sobrescribirla (no borrarla) evita que la reponga.
        response.headers["Server"] = "api"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


def _register_exception_handlers(app: FastAPI) -> None:
    """Traduce las excepciones de dominio a respuestas HTTP uniformes y las loguea."""

    status_map: dict[type[DomainError], int] = {
        NotFoundError: 404,
        AlreadyExistsError: 409,
        InvalidCredentialsError: 401,
        ForbiddenError: 403,
        AccountLockedError: 429,
    }

    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        status_code = status_map.get(type(exc), 400)
        headers: dict[str, str] | None = None
        if status_code == 401:
            headers = {"WWW-Authenticate": "Bearer"}
        elif isinstance(exc, AccountLockedError):
            headers = {"Retry-After": str(exc.retry_after)}

        # 5xx (errores no anticipados) se loguean como error; los 4xx (validación,
        # permisos, credenciales) son parte del flujo normal y se loguean como warning.
        log_level = logging.ERROR if status_code >= 500 else logging.WARNING
        logger.log(
            log_level,
            "Excepción de dominio: %s",
            exc.message,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "exc_type": type(exc).__name__,
            },
        )

        return JSONResponse(
            status_code=status_code,
            content={"detail": exc.message},
            headers=headers,
        )

    app.add_exception_handler(DomainError, domain_error_handler)


def create_app() -> FastAPI:
    """Construye y configura la aplicación FastAPI."""

    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
        # /docs, /redoc y /openapi.json exponen el título, la versión y el stack
        # (FastAPI/Starlette) del API: solo se sirven en desarrollo.
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware, max_body_bytes=settings.max_request_body_bytes)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        # allow_origins=["*"] + allow_credentials=True permitía que cualquier origen
        # hiciera peticiones autenticadas (cookies/Authorization) contra el API.
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        # El frontend necesita leer el nombre del fichero al descargar la plantilla .xlsx.
        expose_headers=["Content-Disposition"],
    )

    _register_exception_handlers(app)

    app.include_router(auth.router)
    app.include_router(users.router)
    app.include_router(bets.router)
    app.include_router(statistics.router)
    app.include_router(ranking.router)
    app.include_router(achievements.router)
    app.include_router(ranks.router)

    @app.get("/health", tags=["health"], summary="Comprobación de salud")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
