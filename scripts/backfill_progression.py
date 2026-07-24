"""Carga inicial manual de progresión: reemplaza el backfill bloqueante del arranque (T-029).

El monolito ya no recalcula estadísticas/progresión de todos los usuarios al iniciar
(``main.py``). En su lugar, este script se ejecuta una vez, manualmente: por cada usuario
con al menos una apuesta existente, publica un evento histórico al exchange ``bets.events``
(el mismo de T-025/T-027). El consumer de progression-service (T-026), ya escuchando la cola
``progression.recalc``, procesa cada evento exactamente igual que uno en vivo: recalcula
stats -> ranks -> logros -> ranking para ese usuario.

Es idempotente: `recalculate` en progression-service relee siempre el estado actual de las
apuestas del usuario, así que volver a ejecutar este script no duplica nada.

Uso:

    poetry run python scripts/backfill_progression.py
    poetry run python scripts/backfill_progression.py --mongo-uri mongodb://localhost:27017 \
        --mongo-db fijazo --rabbitmq-url amqp://fijazo:fijazo@localhost:5672/
    poetry run python scripts/backfill_progression.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import logging

import aio_pika

from fijazo_api.core.config import get_settings
from fijazo_api.domain.entities.bet_event import BetEvent, BetEventType
from fijazo_api.infrastructure.database.mongo import create_client, get_database
from fijazo_api.infrastructure.events.rabbitmq_publisher import RabbitMqBetEventPublisher
from fijazo_api.infrastructure.repositories.mongo_bet_repository import MongoBetRepository

logger = logging.getLogger(__name__)


async def run(mongo_uri: str, mongo_db: str, rabbitmq_url: str, *, dry_run: bool) -> int:
    """Publica un evento histórico por cada usuario con apuestas. Devuelve cuántos."""

    client = create_client(mongo_uri)
    db = get_database(client, mongo_db)
    bets = MongoBetRepository(db)

    try:
        user_ids = await bets.distinct_user_ids()
    finally:
        await client.close()

    if dry_run:
        logger.info("[dry-run] %d usuario(s) recibirían un evento histórico.", len(user_ids))
        return len(user_ids)

    connection = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await connection.channel()
        exchange = await channel.get_exchange(get_settings().bets_events_exchange)
        publisher = RabbitMqBetEventPublisher(exchange)

        for user_id in user_ids:
            event = BetEvent(event_type=BetEventType.CREATED, user_id=user_id, bet_id="backfill")
            await publisher.publish(event)
    finally:
        await connection.close()

    logger.info("Carga inicial publicada para %d usuario(s).", len(user_ids))
    return len(user_ids)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mongo-uri", default=settings.mongo_uri)
    parser.add_argument("--mongo-db", default=settings.mongo_db_name)
    parser.add_argument("--rabbitmq-url", default=settings.rabbitmq_url or "")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Sólo cuenta los usuarios que recibirían un evento, sin publicar nada.",
    )
    args = parser.parse_args()

    if not args.dry_run and not args.rabbitmq_url:
        raise SystemExit(
            "Falta --rabbitmq-url (o RABBITMQ_URL en el entorno). Usa --dry-run para "
            "sólo contar usuarios sin publicar."
        )

    asyncio.run(run(args.mongo_uri, args.mongo_db, args.rabbitmq_url, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
