"""Entrypoint del consumer de eventos de progresión.

Proceso independiente del servidor HTTP: abre la conexión a Mongo y a RabbitMQ y consume
la cola ``progression.recalc`` hasta recibir una señal de parada.

    python -m progression_service.consumer
"""

from __future__ import annotations

import asyncio
import logging

from progression_service.application.factory import build_progression_service
from progression_service.core.config import settings
from progression_service.core.logging import setup_logging
from progression_service.infrastructure.database.mongo import (
    create_client,
    ensure_indexes,
    get_database,
)
from progression_service.infrastructure.messaging.recalc_consumer import RecalcConsumer

logger = logging.getLogger(__name__)


async def run() -> None:
    setup_logging("DEBUG" if settings.debug else "INFO")
    client = create_client(
        settings.mongo_uri,
        max_pool_size=settings.mongo_max_pool_size,
        server_selection_timeout_ms=settings.mongo_server_selection_timeout_ms,
    )
    db = get_database(client, settings.mongo_db_name)
    await ensure_indexes(db)

    consumer = RecalcConsumer(
        settings.rabbitmq_url,
        settings.recalc_queue,
        build_progression_service(db),
        prefetch=settings.recalc_prefetch,
    )
    connection = await consumer.start()
    stop = asyncio.Event()
    try:
        await stop.wait()  # corre hasta cancelación (SIGINT/SIGTERM)
    finally:
        await connection.close()
        await client.close()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("Consumer detenido")


if __name__ == "__main__":
    main()
