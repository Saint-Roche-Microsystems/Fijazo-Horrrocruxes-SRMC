"""Puertos (interfaces) de la capa de aplicación.

Permiten que un caso de uso dependa de una capacidad abstracta en lugar de una
implementación concreta, evitando acoplamiento y ciclos de import.
"""

from typing import Protocol


class StatisticsSynchronizer(Protocol):
    """Capacidad de recalcular las estadísticas de un usuario.

    La implementa :class:`StatisticsService`. ``BetService`` la usa para
    mantener el ranking sincronizado tras cada mutación de apuestas.
    """

    async def recalculate(self, user_id: str) -> None: ...


class AuditLogger(Protocol):
    """Capacidad de registrar un evento crítico (sesión, gestión de usuarios, ...).

    La implementa :class:`MongoAuditLogRepository`. ``AuthService`` y ``UserService``
    la usan para dejar constancia de eventos sensibles en la colección ``audit_logs``,
    separada del log técnico (stdout) de peticiones/excepciones.
    """

    async def log(
        self,
        event_type: str,
        message: str,
        *,
        user_id: str | None = None,
        email: str | None = None,
        meta: dict[str, object] | None = None,
    ) -> None: ...
