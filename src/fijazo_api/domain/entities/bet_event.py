"""Evento de dominio emitido tras una mutación de apuesta.

Entidad pura: describe *qué pasó*, no cómo se transporta. Sustituye a la llamada directa
que ``BetService`` hacía a ``ProgressionService`` (``stats_sync``, retirada en T-028): ahora
se publica al exchange ``bets.events`` de RabbitMQ, el mismo que usa bets-service.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class BetEventType(str, Enum):
    """Mutaciones de apuesta que interesan a progression-service.

    Son las claves de enrutado del exchange topic ``bets.events``, del que
    progression-service consume por la cola ``progression.recalc`` (binding ``bet.#``).
    """

    CREATED = "bet.created"
    UPDATED = "bet.updated"
    DELETED = "bet.deleted"


@dataclass(frozen=True)
class BetEvent:
    """Una mutación de apuesta ya ocurrida.

    ``user_id`` es lo único que progression-service necesita: su recálculo es por
    usuario y relee las apuestas desde su propia fuente.
    """

    event_type: BetEventType
    user_id: str
    bet_id: str
    request_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def as_message(self) -> dict[str, object]:
        """Representación serializable del evento, tal y como viaja por el bus."""

        return {
            "event_type": self.event_type.value,
            "user_id": self.user_id,
            "bet_id": self.bet_id,
            "request_id": self.request_id,
            "occurred_at": self.occurred_at.isoformat(),
        }
