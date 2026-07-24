"""Tests del consumer de recálculo (sin broker: se inyectan dobles)."""

import contextlib

from progression_service.infrastructure.messaging.recalc_consumer import RecalcConsumer


class FakeProgressionService:
    def __init__(self) -> None:
        self.recalculated: list[str] = []

    async def recalculate(self, user_id: str):
        self.recalculated.append(user_id)
        return None


class FakeMessage:
    """Imita ``AbstractIncomingMessage`` en lo que usa el consumer."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def process(self, *, requeue: bool = True, ignore_processed: bool = False):
        @contextlib.asynccontextmanager
        async def _cm():
            yield self

        return _cm()


def _consumer(service) -> RecalcConsumer:
    return RecalcConsumer("amqp://x", "progression.recalc", service)


async def test_valid_event_triggers_recalculate():
    service = FakeProgressionService()
    msg = FakeMessage(b'{"event_type":"bet.created","user_id":"u42","bet_id":"b"}')

    await _consumer(service)._on_message(msg)

    assert service.recalculated == ["u42"]


async def test_event_without_user_id_is_ignored():
    service = FakeProgressionService()
    msg = FakeMessage(b'{"event_type":"bet.created","bet_id":"b"}')

    await _consumer(service)._on_message(msg)

    assert service.recalculated == []


async def test_malformed_body_is_ignored():
    service = FakeProgressionService()
    msg = FakeMessage(b"not-json")

    await _consumer(service)._on_message(msg)

    assert service.recalculated == []


def test_extract_user_id_parsing():
    extract = RecalcConsumer._extract_user_id
    assert extract(b'{"user_id":"abc"}') == "abc"
    assert extract(b'{"user_id":""}') is None
    assert extract(b'{"user_id":123}') is None
    assert extract(b"garbage") is None
