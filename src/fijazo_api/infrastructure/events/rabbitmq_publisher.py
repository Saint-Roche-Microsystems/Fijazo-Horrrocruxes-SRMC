"""Publisher real del puerto :class:`~fijazo_api.application.ports.BetEventPublisher`.

Publica al exchange topic ``bets.events`` (T-025) con routing key igual al tipo de evento,
el mismo exchange que usa bets-service: progression-service no distingue si la apuesta
mutó en el monolito legado o en el servicio extraído.
"""

from __future__ import annotations

import json

import aio_pika

from fijazo_api.domain.entities.bet_event import BetEvent


class RabbitMqBetEventPublisher:
    """Publica eventos de apuesta en el exchange ``bets.events`` de RabbitMQ."""

    def __init__(self, exchange: aio_pika.abc.AbstractExchange) -> None:
        self._exchange = exchange

    async def publish(self, event: BetEvent) -> None:
        body = json.dumps(event.as_message(), separators=(",", ":")).encode("utf-8")
        message = aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=event.event_type.value)
