"""Configuración de la aplicación cargada desde variables de entorno / .env."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Ajustes de la aplicación.

    Los valores se leen de variables de entorno (o de un archivo ``.env``).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Aplicación
    app_name: str = "Fijazo API"
    app_description: str = (
        "API para gestionar apuestas deportivas y el historial personal de cada usuario."
    )
    app_version: str = "0.1.0"
    # En producción se ocultan /docs, /redoc y /openapi.json (filtran versión de
    # FastAPI/Starlette y del propio API) y se limita el tamaño máximo de petición.
    debug: bool = False
    max_request_body_bytes: int = 2 * 1024 * 1024

    # CORS: orígenes del frontend autorizados (separados por comas en la variable de entorno).
    # NoDecode evita que pydantic-settings intente parsear la variable como JSON: del formato
    # se encarga el validador de abajo.
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # Regex opcional de orígenes permitidos, para cubrir las URLs cambiantes de los preview
    # deployments de Vercel (p. ej. `https://fijazo-.*\.vercel\.app`). Se combina con
    # `cors_origins`, que sigue siendo la lista de orígenes fijos.
    cors_origin_regex: str | None = None

    # MongoDB
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db_name: str = "fijazo"
    # Conexiones por instancia. En serverless el total contra Atlas es instancias × este
    # valor, así que conviene mantenerlo bajo.
    mongo_max_pool_size: int = 10
    mongo_server_selection_timeout_ms: int = 10_000

    # Seguridad / JWT
    jwt_secret: str = "change-me-in-production-please-use-a-secure-random-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24

    # Usuario administrador inicial (seed). El dominio debe ser real: los endpoints validan el
    # email con EmailStr, que rechaza dominios reservados como `.local`, así que un admin
    # sembrado con `.local` se crearía pero no podría iniciar sesión nunca.
    admin_username: str = "admin"
    admin_email: str = "admin@fijazo.com"
    admin_password: str = "changeme123"

    # Logging: nivel raíz de la app (DEBUG/INFO/WARNING/ERROR). Los logs se emiten en JSON
    # (ver core/logging.py), un registro por petición REST más uno por excepción.
    log_level: str = "INFO"

    # RabbitMQ: publisher de eventos de dominio (T-028) hacia el exchange declarado en
    # T-025, el mismo que usa bets-service. Con la URL vacía se usa el publisher de log de
    # desarrollo (ver infrastructure/events/logging_publisher.py).
    rabbitmq_url: str | None = None
    bets_events_exchange: str = "bets.events"

    # Hardening de login: tras ``login_max_attempts`` fallos consecutivos sobre la misma
    # cuenta, se bloquea temporalmente con backoff exponencial:
    # ``login_lockout_base_seconds * 2^(intentos_extra)``, con tope en
    # ``login_lockout_max_seconds``. El contador y el bloqueo se guardan en el propio
    # documento del usuario (persisten entre instancias/arranques en frío) y se resetean
    # al iniciar sesión con éxito.
    login_max_attempts: int = 5
    login_lockout_base_seconds: int = 30
    login_lockout_max_seconds: int = 900

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, value: object) -> object:
        """Permite definir CORS_ORIGINS como lista separada por comas."""

        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia cacheada de :class:`Settings`."""

    return Settings()
