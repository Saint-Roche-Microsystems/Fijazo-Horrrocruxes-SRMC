"""Conexión a MongoDB usando el driver async oficial de PyMongo."""

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase


def create_client(
    mongo_uri: str,
    *,
    max_pool_size: int = 10,
    server_selection_timeout_ms: int = 10_000,
) -> AsyncMongoClient:
    """Crea un cliente async de MongoDB.

    ``tz_aware=True`` hace que las fechas leídas vuelvan como *aware* (UTC), de
    modo que se pueden comparar con ``datetime.now(timezone.utc)`` sin errores.

    Los valores por defecto están pensados para entornos serverless (Vercel), donde cada
    instancia mantiene su propio pool y el total de conexiones simultáneas contra Atlas es
    ``instancias × max_pool_size``: un pool pequeño evita agotar el límite del cluster. El
    timeout de selección de servidor se recorta respecto a los 30 s por defecto para que un
    fallo de red devuelva un error rápido en lugar de consumir toda la duración de la
    función.
    """

    return AsyncMongoClient(
        mongo_uri,
        tz_aware=True,
        maxPoolSize=max_pool_size,
        serverSelectionTimeoutMS=server_selection_timeout_ms,
    )


def get_database(client: AsyncMongoClient, db_name: str) -> AsyncDatabase:
    """Devuelve la base de datos indicada del cliente."""

    return client[db_name]


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Crea los índices necesarios (idempotente).

    - ``users.email`` y ``users.username`` únicos (refuerza la unicidad).
    - ``bets.user_id`` para acelerar el listado por usuario.
    - ``user_statistics.user_id`` único y ``ranking_score`` (desc) para el ranking.
    - ``audit_logs.created_at`` con TTL (90 días) y ``audit_logs.user_id`` para consultas
      por usuario.
    """

    await db["users"].create_index("email", unique=True)
    await db["users"].create_index("username", unique=True)
    await db["bets"].create_index("user_id")
    await db["bets"].create_index(
        [("user_id", 1), ("reference_id", 1)],
        sparse=True,
    )
    await db["user_statistics"].create_index("user_id", unique=True)
    await db["user_statistics"].create_index([("ranking_score", -1)])
    await db["user_progression"].create_index("user_id", unique=True)
    await db["audit_logs"].create_index("created_at", expireAfterSeconds=60 * 60 * 24 * 90)
    await db["audit_logs"].create_index("user_id")
