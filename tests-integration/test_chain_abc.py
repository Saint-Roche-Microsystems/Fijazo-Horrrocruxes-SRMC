"""Test de integración de la cadena síncrona completa A->B->C (T-018).

Ejercita, contra los tres contenedores reales levantados por
``docker-compose.yml`` de este directorio (sin stubs):

    bets-service --TCP--> users-service --HTTP--> auth-service

Un registro real en auth-service crea la credencial y propaga el perfil a
users-service (``POST /internal/users``); bets-service valida a ese usuario contra
users-service (``users.validate``, TCP), que a su vez consulta el estado de bloqueo en
auth-service (``GET /internal/lock-status``, HTTP). Se verifica que el resultado
combinado (``active``, ``tier``, ``locked``) llega correctamente hasta bets-service,
tanto para una cuenta normal como para una bloqueada por intentos fallidos de login.

Uso:

    docker compose -f tests-integration/docker-compose.yml up -d --build
    poetry run pytest tests-integration/test_chain_abc.py -q
    docker compose -f tests-integration/docker-compose.yml down -v
"""

import time
import uuid

import httpx
import pytest

AUTH_URL = "http://localhost:8001"
USERS_URL = "http://localhost:3001"
BETS_URL = "http://localhost:8002"
INTERNAL_KEY = "e2e-test-internal-key"
LOGIN_MAX_ATTEMPTS = 5


def _wait_healthy(url: str, timeout_s: float = 60.0) -> None:
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


def _register(username: str, email: str, password: str = "secret123") -> str:
    """Registra en auth-service (crea credencial + propaga perfil a users-service).

    Devuelve el ``user_id`` compartido por ambos servicios.
    """

    resp = httpx.post(
        f"{AUTH_URL}/auth/register",
        json={"username": username, "email": email, "password": password},
        timeout=10.0,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _wait_profile_synced(user_id: str, timeout_s: float = 10.0) -> None:
    """Espera a que el perfil propagado por auth-service exista en users-service."""

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = httpx.get(f"{USERS_URL}/users/{user_id}", timeout=5.0)
        if resp.status_code == 200:
            return
        time.sleep(0.5)
    raise RuntimeError(f"El perfil de {user_id} nunca se propagó a users-service.")


def _create_bet(user_id: str) -> httpx.Response:
    return httpx.post(
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
            "status": "PENDING",
        },
        headers={"X-User-Id": user_id, "X-Internal-Key": INTERNAL_KEY},
        timeout=10.0,
    )


def test_active_unlocked_user_reaches_bets_service():
    """Cuenta normal: active=True, locked=False llega hasta bets-service -> 201."""

    suffix = uuid.uuid4().hex[:6]
    user_id = _register(f"e2eok{suffix}", f"abc_ok_{suffix}@fijazo.com")
    _wait_profile_synced(user_id)

    resp = _create_bet(user_id)
    assert resp.status_code == 201, resp.text


def test_locked_user_is_rejected_by_bets_service():
    """Una cuenta bloqueada en auth-service (intentos fallidos) llega como locked=True
    hasta bets-service a través de users-service, y la apuesta se rechaza."""

    suffix = uuid.uuid4().hex[:6]
    email = f"abc_locked_{suffix}@fijazo.com"
    user_id = _register(f"e2elk{suffix}", email)
    _wait_profile_synced(user_id)

    # Agota los intentos permitidos con la contraseña equivocada -> bloqueo real.
    for _ in range(LOGIN_MAX_ATTEMPTS):
        httpx.post(
            f"{AUTH_URL}/auth/login",
            json={"email": email, "password": "wrong-password"},
            timeout=10.0,
        )

    resp = _create_bet(user_id)
    assert resp.status_code == 403, resp.text
    assert "bloqueada" in resp.json()["detail"]


def test_unknown_user_is_treated_as_inactive():
    """Un user_id que no existe en users-service se trata como inactivo, no como error."""

    resp = _create_bet("000000000000000000000000")
    assert resp.status_code == 403
    assert "desactivada" in resp.json()["detail"]
