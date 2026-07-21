"""Persistencia de eventos críticos (sesión, gestión de usuarios) en MongoDB.

Separada del log técnico de peticiones/excepciones (stdout, ver core/logging.py):
esta colección solo guarda eventos de negocio relevantes para auditoría —
login, registro, cambios de estado de usuario, etc. — con retención acotada
mediante índice TTL (ver ``ensure_indexes`` en infrastructure/database/mongo.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo.asynchronous.database import AsyncDatabase

from fijazo_api.core.logging import get_request_id

logger = logging.getLogger(__name__)


class MongoAuditLogRepository:
    """Implementa el puerto :class:`~fijazo_api.application.ports.AuditLogger`."""

    def __init__(self, db: AsyncDatabase) -> None:
        self._collection = db["audit_logs"]

    async def log(
        self,
        event_type: str,
        message: str,
        *,
        user_id: str | None = None,
        email: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None:
        document = {
            "event_type": event_type,
            "message": message,
            "user_id": user_id,
            "email": email,
            "meta": meta or {},
            "request_id": get_request_id(),
            "created_at": datetime.now(timezone.utc),
        }

        # Un fallo al auditar no debe tumbar la petición del usuario: se registra en el
        # log técnico y se sigue.
        try:
            await self._collection.insert_one(document)
        except Exception:
            logger.exception("No se pudo escribir el evento de auditoría '%s'", event_type)
