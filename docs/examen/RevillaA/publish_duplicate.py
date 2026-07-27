"""Publica el mismo bet.created dos veces al exchange bets.events, simulando la
redelivery "al menos una vez" de RabbitMQ. Evidencia para la Actividad C (examen final).
"""

import asyncio
import json
import sys

import aio_pika

USER_ID = "6a60c83b2a0af5b4ab9745cf"
BET_ID = "6a617db47729546dc1a36341"
OCCURRED_AT = "2026-07-27T12:05:00+00:00"


async def main() -> None:
    connection = await aio_pika.connect_robust("amqp://fijazo:fijazo@localhost:5672/")
    async with connection:
        channel = await connection.channel()
        exchange = await channel.get_exchange("bets.events")

        payload = {
            "event_type": "bet.created",
            "user_id": USER_ID,
            "bet_id": BET_ID,
            "request_id": "evidencia-examen-revillaa",
            "occurred_at": OCCURRED_AT,
        }
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

        for i in (1, 2):
            await exchange.publish(
                aio_pika.Message(body=body, content_type="application/json"),
                routing_key="bet.created",
            )
            print(f"Publicado #{i}: {payload}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
