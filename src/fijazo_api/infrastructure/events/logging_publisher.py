"""Implementación de desarrollo del puerto :class:`~fijazo_api.application.ports.BetEventPublisher`.

Emite cada evento como una línea de log JSON. Es la implementación por defecto sin
``RABBITMQ_URL`` configurada: deja el circuito verificable sin levantar el broker.
"""

from __future__ import annotations

import logging

from fijazo_api.domain.entities.bet_event import BetEvent

logger = logging.getLogger(__name__)


class LoggingBetEventPublisher:
    """Registra el evento en stdout en lugar de publicarlo en un bus."""

    async def publish(self, event: BetEvent) -> None:
        logger.info(
            "Evento de dominio: %s",
            event.event_type.value,
            extra={"event": event.as_message()},
        )
