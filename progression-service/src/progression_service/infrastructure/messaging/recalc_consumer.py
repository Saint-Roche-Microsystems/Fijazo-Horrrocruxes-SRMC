"""Consumer de eventos de apuesta: dispara el recálculo de progresión por usuario.

Escucha la cola ``progression.recalc`` (enlazada al exchange ``bets.events``). Cada mensaje
publicado por bets-service tras una mutación de apuesta contiene el ``user_id`` afectado;
al recibirlo se ejecuta la cadena completa stats -> ranks -> logros -> ranking para ese
usuario, releyendo sus apuestas desde la propia base del servicio.
"""

from __future__ import annotations

import json
import logging

import aio_pika

from progression_service.application.services.progression_service import ProgressionService

logger = logging.getLogger(__name__)


class RecalcConsumer:
    """Suscribe la cola de recálculo y ejecuta la progresión por cada evento."""

    def __init__(
        self,
        amqp_url: str,
        queue_name: str,
        progression_service: ProgressionService,
        *,
        prefetch: int = 10,
    ) -> None:
        self._amqp_url = amqp_url
        self._queue_name = queue_name
        self._progression = progression_service
        self._prefetch = prefetch
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None

    async def start(self) -> aio_pika.abc.AbstractRobustConnection:
        """Conecta, declara la cola (idempotente) y empieza a consumir."""

        self._connection = await aio_pika.connect_robust(self._amqp_url)
        channel = await self._connection.channel()
        await channel.set_qos(prefetch_count=self._prefetch)
        # Durable para coincidir con la cola declarada por la infraestructura (T-025).
        queue = await channel.declare_queue(self._queue_name, durable=True)
        await queue.consume(self._on_message)
        logger.info("Consumiendo la cola %s", self._queue_name)
        return self._connection

    async def stop(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _on_message(self, message: aio_pika.abc.AbstractIncomingMessage) -> None:
        # requeue=False: un mensaje que no se puede procesar no debe reencolarse en bucle.
        async with message.process(requeue=False, ignore_processed=True):
            user_id = self._extract_user_id(message.body)
            if user_id is None:
                logger.warning("Evento sin user_id; se descarta: %r", message.body[:200])
                return
            await self._progression.recalculate(user_id)
            logger.info("Progresión recalculada por evento", extra={"user_id": user_id})

    @staticmethod
    def _extract_user_id(body: bytes) -> str | None:
        try:
            payload = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        user_id = payload.get("user_id") if isinstance(payload, dict) else None
        return user_id if isinstance(user_id, str) and user_id else None
