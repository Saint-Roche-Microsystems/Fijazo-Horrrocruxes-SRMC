"""Carga inicial manual de progresión: reemplaza el backfill bloqueante del arranque (T-029).

Ningún servicio recalcula estadísticas/progresión de todos los usuarios al iniciar. En su
lugar, este script se ejecuta una vez, manualmente: por cada usuario con al menos una
apuesta, publica un evento histórico al exchange ``bets.events`` (el mismo de T-025/T-027).
El consumer de progression-service (T-026), escuchando la cola ``progression.recalc``,
procesa cada evento exactamente igual que uno en vivo: recalcula stats -> ranks -> logros
-> ranking para ese usuario.

Es idempotente: `recalculate` en progression-service relee siempre el estado actual de las
apuestas del usuario, así que volver a ejecutar este script no duplica nada.

No abre ninguna base de datos. Las apuestas son de bets-service, así que la lista de
usuarios se pide a su API interna (``GET /internal/bets/user-ids``) con el secreto de
servicio compartido; el script sólo necesita hablar HTTP y AMQP, y no depende del paquete
de ningún microservicio.

Uso:

    poetry run python scripts/backfill_progression.py --dry-run
    poetry run python scripts/backfill_progression.py
    poetry run python scripts/backfill_progression.py \
        --bets-url http://localhost:8002 \
        --rabbitmq-url amqp://fijazo:fijazo@localhost:5672/

Por defecto toma `BETS_SERVICE_URL`, `INTERNAL_API_KEY` y `RABBITMQ_URL` del entorno.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

import aio_pika
import httpx

logger = logging.getLogger(__name__)

# Centinela en lugar de un id real: el evento sólo anuncia QUÉ usuario cambió, y
# progression-service relee su historial completo. Ver el contrato en
# bets-service/src/bets_service/domain/entities/bet_event.py (BetEvent.as_message).
_BACKFILL_BET_ID = "backfill"
_EVENT_TYPE = "bet.created"


async def fetch_user_ids(bets_url: str, internal_key: str, timeout: float) -> list[str]:
    """Usuarios con al menos una apuesta, según su dueño (bets-service)."""

    async with httpx.AsyncClient(
        base_url=bets_url,
        timeout=httpx.Timeout(timeout),
        headers={"X-Internal-Key": internal_key},
    ) as client:
        response = await client.get("/internal/bets/user-ids")
        response.raise_for_status()
        return list(response.json()["user_ids"])


def build_message(user_id: str) -> aio_pika.Message:
    """Evento histórico, con el mismo formato de cable que publica bets-service."""

    body = json.dumps(
        {
            "event_type": _EVENT_TYPE,
            "user_id": user_id,
            "bet_id": _BACKFILL_BET_ID,
            "request_id": None,
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        },
        separators=(",", ":"),
    ).encode("utf-8")

    return aio_pika.Message(
        body=body,
        content_type="application/json",
        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
    )


async def run(
    bets_url: str,
    internal_key: str,
    rabbitmq_url: str,
    exchange_name: str,
    timeout: float,
    *,
    dry_run: bool,
) -> int:
    """Publica un evento histórico por cada usuario con apuestas. Devuelve cuántos."""

    user_ids = await fetch_user_ids(bets_url, internal_key, timeout)

    if dry_run:
        logger.info("[dry-run] %d usuario(s) recibirían un evento histórico.", len(user_ids))
        return len(user_ids)

    connection = await aio_pika.connect_robust(rabbitmq_url)
    try:
        channel = await connection.channel()
        # El exchange lo declara la infraestructura (T-025): aquí sólo se busca.
        exchange = await channel.get_exchange(exchange_name)
        for user_id in user_ids:
            await exchange.publish(build_message(user_id), routing_key=_EVENT_TYPE)
    finally:
        await connection.close()

    logger.info("Carga inicial publicada para %d usuario(s).", len(user_ids))
    return len(user_ids)


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bets-url",
        default=os.environ.get("BETS_SERVICE_URL", "http://localhost:8002"),
    )
    parser.add_argument("--internal-key", default=os.environ.get("INTERNAL_API_KEY", ""))
    parser.add_argument("--rabbitmq-url", default=os.environ.get("RABBITMQ_URL", ""))
    parser.add_argument(
        "--exchange",
        default=os.environ.get("BETS_EVENTS_EXCHANGE", "bets.events"),
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Sólo cuenta los usuarios que recibirían un evento, sin publicar nada.",
    )
    args = parser.parse_args()

    if not args.internal_key:
        raise SystemExit(
            "Falta --internal-key (o INTERNAL_API_KEY en el entorno): la API interna de "
            "bets-service no responde sin el secreto de servicio."
        )

    if not args.dry_run and not args.rabbitmq_url:
        raise SystemExit(
            "Falta --rabbitmq-url (o RABBITMQ_URL en el entorno). Usa --dry-run para "
            "sólo contar usuarios sin publicar."
        )

    asyncio.run(
        run(
            args.bets_url,
            args.internal_key,
            args.rabbitmq_url,
            args.exchange,
            args.timeout,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
