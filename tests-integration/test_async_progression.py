"""Test de integración del circuito asíncrono (T-026/T-027).

Ejercita, contra los contenedores reales de ``docker-compose.yml`` de este directorio:

    bets-service --publish--> RabbitMQ (bets.events) --> cola progression.recalc
        --> progression-service --HTTP--> bets-service (relee el historial)

Es decir: crear una apuesta acaba actualizando las estadísticas del usuario **sin que
nadie llame** a ``POST /internal/recalculate``. Antes de este circuito el mensaje se
quedaba en la cola sin consumidor y la proyección sólo se movía a mano.

El test está construido para fallar si el consumer no existe. La clave es el paso de
"materialización": ``GET /statistics/{user_id}`` usa ``get_or_recalculate``, que devuelve
lo ya almacenado si existe y sólo calcula cuando no hay nada. Si se consultara en frío,
el endpoint recalcularía por su cuenta y el test pasaría igual sin consumer. Consultando
una primera vez para materializar, el segundo cambio sólo puede llegar por el evento.

Uso:

    docker compose -f tests-integration/docker-compose.yml up -d --build
    poetry run pytest tests-integration/test_async_progression.py -q
    docker compose -f tests-integration/docker-compose.yml down -v
"""

import time
import uuid

import httpx
import pytest

AUTH_URL = "http://localhost:8001"
USERS_URL = "http://localhost:3001"
BETS_URL = "http://localhost:8002"
PROGRESSION_URL = "http://localhost:8003"
INTERNAL_KEY = "e2e-test-internal-key"


def _wait_healthy(url: str, timeout_s: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{url}/health", timeout=2.0)
            if resp.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(1.0)
    raise RuntimeError(f"{url}/health nunca respondió 200 a tiempo: {last_error}")


@pytest.fixture(scope="module", autouse=True)
def services_ready():
    _wait_healthy(AUTH_URL)
    _wait_healthy(USERS_URL)
    _wait_healthy(BETS_URL)
    _wait_healthy(PROGRESSION_URL)


def _register(username: str, email: str, password: str = "secret123") -> str:
    resp = httpx.post(
        f"{AUTH_URL}/auth/register",
        json={"username": username, "email": email, "password": password},
        timeout=10.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _wait_profile_synced(user_id: str, timeout_s: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = httpx.get(f"{USERS_URL}/users/{user_id}", timeout=5.0)
        if resp.status_code == 200:
            return
        time.sleep(0.5)
    raise RuntimeError(f"El perfil de {user_id} nunca se propagó a users-service.")


def _create_bet(user_id: str, status: str = "WON") -> str:
    resp = httpx.post(
        f"{BETS_URL}/bets",
        json={
            "sport": "Football",
            "league": "L",
            "event": "A vs B",
            "bet_type": "SIMPLE",
            "market": "1X2",
            "selection": "A",
            "odds": 2.0,
            "stake": 10,
            "bookmaker": "bk",
            "event_datetime": "2026-08-01T20:00:00Z",
            "status": status,
        },
        headers={"X-User-Id": user_id, "X-Internal-Key": INTERNAL_KEY},
        timeout=10.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _statistics(user_id: str) -> dict:
    resp = httpx.get(f"{PROGRESSION_URL}/statistics/{user_id}", timeout=10.0)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _wait_total_bets(user_id: str, expected: int, timeout_s: float = 30.0) -> dict:
    """Sondea hasta que la proyección refleje ``expected`` apuestas.

    Sondeo con deadline en vez de ``sleep`` fijo: el recálculo es asíncrono y su latencia
    depende de la carga del broker y del contenedor.
    """

    deadline = time.monotonic() + timeout_s
    last: dict = {}
    while time.monotonic() < deadline:
        last = _statistics(user_id)
        if last["total_bets"] == expected:
            return last
        time.sleep(0.5)
    raise AssertionError(
        f"Las estadísticas de {user_id} nunca llegaron a {expected} apuestas "
        f"(última lectura: total_bets={last.get('total_bets')}). "
        "¿Está vivo el consumer de progression.recalc?"
    )


def _new_user() -> str:
    suffix = uuid.uuid4().hex[:6]
    user_id = _register(f"e2eas{suffix}", f"async_{suffix}@fijazo.com")
    _wait_profile_synced(user_id)
    return user_id


def test_creating_a_bet_updates_statistics_without_manual_recalculation():
    user_id = _new_user()

    _create_bet(user_id)
    # Materializa la proyección: a partir de aquí, GET /statistics devuelve lo almacenado
    # y ya no recalcula solo. Sin esto el test pasaría aunque no hubiera consumer.
    assert _wait_total_bets(user_id, 1)["total_bets"] == 1

    _create_bet(user_id)

    # Este segundo cambio sólo puede llegar por el evento de RabbitMQ.
    stats = _wait_total_bets(user_id, 2)
    assert stats["total_bets"] == 2


def test_deleting_a_bet_also_propagates():
    user_id = _new_user()

    _create_bet(user_id)
    bet_id = _create_bet(user_id)
    _wait_total_bets(user_id, 2)

    resp = httpx.delete(
        f"{BETS_URL}/bets/{bet_id}",
        headers={"X-User-Id": user_id, "X-Internal-Key": INTERNAL_KEY},
        timeout=10.0,
    )
    assert resp.status_code in (200, 204), resp.text

    # bet.deleted usa el mismo binding `bet.#` que bet.created.
    _wait_total_bets(user_id, 1)


def test_recalculation_is_idempotent_across_repeated_events():
    """Reprocesar no duplica: el evento sólo avisa, el historial se relee entero."""

    user_id = _new_user()
    _create_bet(user_id)
    _wait_total_bets(user_id, 1)

    # Un disparo manual extra equivale a recibir el mismo evento dos veces.
    resp = httpx.post(
        f"{PROGRESSION_URL}/internal/recalculate/{user_id}",
        headers={"X-Internal-Key": INTERNAL_KEY},
        timeout=10.0,
    )
    assert resp.status_code == 200, resp.text

    assert _statistics(user_id)["total_bets"] == 1
