"""Tests de los eventos de dominio que sustituyen al recálculo en proceso (T-028).

``BetService`` ya no llama a ``ProgressionService`` tras cada mutación: publica un
evento y devuelve. Lo que hay que fijar aquí es *qué* se publica y *cuándo*, igual que
en bets-service (``tests/test_events.py``).
"""

from httpx import AsyncClient

from fijazo_api.api.deps import get_event_publisher
from fijazo_api.domain.entities.bet_event import BetEvent, BetEventType
from fijazo_api.main import app
from tests.conftest import auth_header, register_and_login, sample_bet_payload


class RecordingPublisher:
    """Guarda en memoria los eventos publicados."""

    def __init__(self) -> None:
        self.events: list[BetEvent] = []

    async def publish(self, event: BetEvent) -> None:
        self.events.append(event)

    @property
    def types(self) -> list[str]:
        return [e.event_type.value for e in self.events]


class BrokenPublisher:
    """Simula el bus caído."""

    async def publish(self, event: BetEvent) -> None:
        raise ConnectionError("RabbitMQ no responde.")


async def _headers(client: AsyncClient, username: str, email: str) -> dict:
    token = await register_and_login(client, username, email)
    return auth_header(token)


async def test_create_publishes_bet_created(client: AsyncClient):
    recorder = RecordingPublisher()
    app.dependency_overrides[get_event_publisher] = lambda: recorder
    try:
        h = await _headers(client, "evtuser1", "evt1@test.com")
        resp = await client.post("/bets", json=sample_bet_payload(), headers=h)

        assert recorder.types == [BetEventType.CREATED.value]
        assert recorder.events[0].bet_id == resp.json()["id"]
    finally:
        app.dependency_overrides.pop(get_event_publisher, None)


async def test_update_and_delete_publish_their_events(client: AsyncClient):
    recorder = RecordingPublisher()
    app.dependency_overrides[get_event_publisher] = lambda: recorder
    try:
        h = await _headers(client, "evtuser2", "evt2@test.com")
        created = await client.post("/bets", json=sample_bet_payload(), headers=h)
        bet_id = created.json()["id"]

        await client.put(f"/bets/{bet_id}", json={"odds": 3.0}, headers=h)
        await client.delete(f"/bets/{bet_id}", headers=h)

        assert recorder.types == [
            BetEventType.CREATED.value,
            BetEventType.UPDATED.value,
            BetEventType.DELETED.value,
        ]
    finally:
        app.dependency_overrides.pop(get_event_publisher, None)


async def test_publisher_failure_does_not_break_the_request(client: AsyncClient):
    app.dependency_overrides[get_event_publisher] = lambda: BrokenPublisher()
    try:
        h = await _headers(client, "evtuser3", "evt3@test.com")
        resp = await client.post("/bets", json=sample_bet_payload(), headers=h)

        assert resp.status_code == 201  # ya persistida: el bus caído no revierte nada
    finally:
        app.dependency_overrides.pop(get_event_publisher, None)
