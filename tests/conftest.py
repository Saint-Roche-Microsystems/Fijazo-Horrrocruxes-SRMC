"""Fixtures compartidas para los tests de integración.

Requieren una instancia de MongoDB accesible (por defecto en
``mongodb://localhost:27017``; configurable con ``TEST_MONGO_URI``). Con
docker-compose basta con levantar el servicio ``mongo``.
"""

import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pymongo import AsyncMongoClient

from fijazo_api.api.deps import get_db
from fijazo_api.infrastructure.database.mongo import ensure_indexes
from fijazo_api.main import app

TEST_MONGO_URI = os.getenv("TEST_MONGO_URI", "mongodb://localhost:27017")
TEST_DB_NAME = os.getenv("TEST_DB_NAME", "fijazo_test")


@pytest_asyncio.fixture
async def test_db():
    """Base de datos de test limpia con los índices creados."""

    client = AsyncMongoClient(TEST_MONGO_URI, tz_aware=True)  # igual que producción
    db = client[TEST_DB_NAME]

    # Estado limpio antes del test.
    await db["users"].drop()
    await db["bets"].drop()
    await db["user_statistics"].drop()
    await db["user_progression"].drop()
    await ensure_indexes(db)

    try:
        yield db
    finally:
        await db["users"].drop()
        await db["bets"].drop()
        await db["user_statistics"].drop()
        await db["user_progression"].drop()
        await client.close()


@pytest_asyncio.fixture
async def client(test_db):
    """Cliente HTTP asíncrono con la BD de test inyectada."""

    app.dependency_overrides[get_db] = lambda: test_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def register_and_login(
    client: AsyncClient, username: str, email: str, password: str = "password123"
) -> str:
    """Helper: registra un usuario, inicia sesión y devuelve el token."""

    await client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    resp = await client.post("/auth/login", json={"email": email, "password": password})
    return resp.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def sample_bet_payload(**overrides) -> dict:
    """Payload válido de apuesta para reutilizar en los tests."""

    payload = {
        "sport": "Fútbol",
        "league": "LaLiga",
        "event": "Real Madrid vs Barcelona",
        "bet_type": "SIMPLE",
        "market": "1X2",
        "selection": "Real Madrid",
        "odds": 2.0,
        "stake": 10.0,
        "bookmaker": "Bet365",
        "event_datetime": "2026-08-01T20:00:00Z",
        "status": "PENDING",
        "notes": "El clásico",
        "reference_id": "ABC123",
    }
    payload.update(overrides)
    return payload
