"""Puertos (interfaces) de la capa de aplicación.

Permiten que un caso de uso dependa de una capacidad abstracta en lugar de una
implementación concreta, evitando acoplamiento y ciclos de import.
"""

from typing import Protocol

from fijazo_api.domain.entities.bet_event import BetEvent


class BetEventPublisher(Protocol):
    """Capacidad de anunciar que una apuesta cambió.

    Sustituye a la llamada directa que ``BetService`` hacía a ``ProgressionService``
    (``StatisticsSynchronizer``, retirada en T-028): ahora la respuesta al cliente no
    espera al recálculo de estadísticas, rangos, logros y ranking, que ocurre en
    progression-service al consumir el exchange ``bets.events``.

    Publicar no debe poder tumbar la operación: la apuesta ya está persistida y es la
    fuente de verdad. Una implementación que falle debe registrarlo y devolver el
    control, no propagar la excepción.
    """

    async def publish(self, event: BetEvent) -> None: ...


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
