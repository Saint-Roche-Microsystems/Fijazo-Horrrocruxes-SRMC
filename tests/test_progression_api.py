"""Tests de integración de rangos y logros (API + sincronización)."""

from httpx import AsyncClient

from tests.conftest import auth_header, register_and_login, sample_bet_payload


async def _create_bet(client: AsyncClient, headers: dict, **overrides) -> str:
    resp = await client.post("/bets", json=sample_bet_payload(**overrides), headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _settle(client: AsyncClient, headers: dict, bet_id: str, status: str) -> None:
    resp = await client.put(f"/bets/{bet_id}", json={"status": status}, headers=headers)
    assert resp.status_code == 200


async def test_catalog_and_ranks_public_lists(client: AsyncClient):
    token = await register_and_login(client, "cataloguser", "cat@test.com")
    h = auth_header(token)

    ach = await client.get("/achievements", headers=h)
    assert ach.status_code == 200
    assert len(ach.json()) >= 20  # catálogo completo
    assert {"id", "name", "category", "icon"} <= set(ach.json()[0])

    ranks = await client.get("/ranks", headers=h)
    assert ranks.status_code == 200
    names = [r["name"] for r in ranks.json()]
    assert names[0] == "Novato" and names[-1] == "Leyenda"


async def test_achievements_unlock_on_first_read(client: AsyncClient):
    """La primera lectura de ``/achievements/me`` evalúa y cachea la progresión.

    Sin sincronización en proceso (T-028), esa lectura ya no se vuelve a disparar
    tras cada mutación: el recálculo real (incluidos logros que dependen de rachas,
    como ``streak_3``) ocurre en progression-service al consumir el evento de
    RabbitMQ (T-026), no aquí. Este test cubre únicamente el desbloqueo inicial;
    la idempotencia de la evaluación (no duplicar logros ya obtenidos) está cubierta
    a nivel de dominio en ``test_achievement_evaluator.py``.
    """

    token = await register_and_login(client, "achuser", "ach@test.com")
    h = auth_header(token)

    # Primera apuesta -> desbloquea "exp_first".
    await _create_bet(client, h)
    me = await client.get("/achievements/me", headers=h)
    data = me.json()
    unlocked = {a["id"] for a in data["achievements"] if a["unlocked"]}
    assert "exp_first" in unlocked
    assert data["unlocked_count"] == len(unlocked)
    first = next(a for a in data["achievements"] if a["id"] == "exp_first")
    assert first["obtained_at"] is not None


async def test_ranks_me_progress(client: AsyncClient):
    token = await register_and_login(client, "rankuser", "rank@test.com")
    h = auth_header(token)
    await _create_bet(client, h)

    resp = await client.get("/ranks/me", headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["current"]["name"] == "Novato"  # recién empieza
    assert 0.0 <= body["progress"] <= 100.0
    assert "rank_score" in body
    assert body["next"]["name"] == "Principiante"
