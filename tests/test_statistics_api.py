"""Tests de integración de estadísticas y ranking (API + sincronización)."""

from httpx import AsyncClient

from tests.conftest import auth_header, register_and_login, sample_bet_payload


async def _create_bet(client: AsyncClient, headers: dict, **overrides) -> str:
    resp = await client.post("/bets", json=sample_bet_payload(**overrides), headers=headers)
    assert resp.status_code == 201
    return resp.json()["id"]


async def _settle(client: AsyncClient, headers: dict, bet_id: str, status: str) -> None:
    resp = await client.put(f"/bets/{bet_id}", json={"status": status}, headers=headers)
    assert resp.status_code == 200


async def test_statistics_me_reflects_bets(client: AsyncClient):
    token = await register_and_login(client, "statuser", "stat@test.com")
    h = auth_header(token)

    won = await _create_bet(client, h, odds=2.0, stake=10)
    lost = await _create_bet(client, h, odds=2.0, stake=10)
    await _create_bet(client, h)  # queda PENDING
    await _settle(client, h, won, "WON")
    await _settle(client, h, lost, "LOST")

    resp = await client.get("/statistics/me", headers=h)
    assert resp.status_code == 200
    s = resp.json()
    assert s["total_bets"] == 3
    assert s["won"] == 1 and s["lost"] == 1 and s["pending"] == 1
    assert s["win_rate"] == 50.0
    assert s["net_profit"] == 0.0  # +10 y -10
    assert s["roi"] == 0.0
    assert "ranking_score" in s


async def test_statistics_are_cached_after_first_read(client: AsyncClient):
    """Sin sincronización en proceso (T-028), la primera lectura materializa el
    documento y las mutaciones posteriores ya no lo actualizan aquí: el recálculo
    real ocurre exclusivamente en progression-service, al consumir el evento de
    RabbitMQ (T-026). Este endpoint queda congelado en el primer cálculo."""

    token = await register_and_login(client, "syncuser", "sync@test.com")
    h = auth_header(token)

    bet_id = await _create_bet(client, h, odds=2.0, stake=10)

    resp = await client.get("/statistics/me", headers=h)
    assert resp.json()["pending"] == 1
    assert resp.json()["won"] == 0

    await _settle(client, h, bet_id, "WON")

    resp = await client.get("/statistics/me", headers=h)
    s = resp.json()
    assert s["pending"] == 1 and s["won"] == 0  # sigue el valor cacheado en la 1ª lectura


async def test_statistics_requires_auth(client: AsyncClient):
    resp = await client.get("/statistics/me")
    assert resp.status_code == 401


async def test_ranking_orders_and_positions(client: AsyncClient):
    # Usuario A: gana ambas. Usuario B: pierde ambas.
    token_a = await register_and_login(client, "usera", "a@test.com")
    token_b = await register_and_login(client, "userb", "b@test.com")
    ha, hb = auth_header(token_a), auth_header(token_b)

    for _ in range(2):
        bid = await _create_bet(client, ha, odds=2.0, stake=10)
        await _settle(client, ha, bid, "WON")
    for _ in range(2):
        bid = await _create_bet(client, hb, odds=2.0, stake=10)
        await _settle(client, hb, bid, "LOST")

    # Sin sincronización en proceso (T-028), el ranking sólo ve a los usuarios cuyas
    # estadísticas ya se materializaron; una lectura de /statistics/me las materializa.
    await client.get("/statistics/me", headers=ha)
    await client.get("/statistics/me", headers=hb)

    resp = await client.get("/ranking", headers=ha)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    usernames = [e["username"] for e in body["items"]]
    assert usernames == ["usera", "userb"]  # A por delante de B
    assert body["items"][0]["position"] == 1
    assert body["items"][1]["position"] == 2

    # Top
    resp = await client.get("/ranking/top?limit=1", headers=ha)
    top = resp.json()
    assert len(top) == 1 and top[0]["username"] == "usera"

    # Posición propia
    resp = await client.get("/ranking/me", headers=hb)
    me = resp.json()
    assert me["position"] == 2
    assert me["entry"]["username"] == "userb"


async def test_ranking_me_without_bets(client: AsyncClient):
    token = await register_and_login(client, "nobets", "nobets@test.com")
    # Sin apuestas, pero /statistics/me materializa el doc (lazy).
    resp = await client.get("/statistics/me", headers=auth_header(token))
    assert resp.status_code == 200
    resp = await client.get("/ranking/me", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["position"] is not None
