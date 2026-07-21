"""Tests del parlay multi-selección (validación, cuota combinada, stats)."""

from httpx import AsyncClient

from tests.conftest import auth_header, register_and_login, sample_bet_payload


def _leg(**overrides) -> dict:
    leg = {
        "sport": "Tenis",
        "league": "ATP",
        "event": "X vs Y",
        "market": "Ganador",
        "selection": "X",
        "odds": 3.0,
    }
    leg.update(overrides)
    return leg


async def test_create_parlay_combines_odds(client: AsyncClient):
    token = await register_and_login(client, "parlayer", "parlay@test.com")
    payload = sample_bet_payload(bet_type="PARLAY", odds=2.0, stake=10, legs=[_leg(odds=3.0)])
    resp = await client.post("/bets", json=payload, headers=auth_header(token))
    assert resp.status_code == 201
    data = resp.json()
    assert data["bet_type"] == "PARLAY"
    assert len(data["legs"]) == 1
    assert data["combined_odds"] == 6.0  # 2.0 * 3.0
    assert data["potential_return"] == 60.0  # 10 * 6
    assert data["potential_profit"] == 50.0


async def test_simple_with_legs_rejected(client: AsyncClient):
    token = await register_and_login(client, "simpleuser", "simple@test.com")
    payload = sample_bet_payload(bet_type="SIMPLE", legs=[_leg()])
    resp = await client.post("/bets", json=payload, headers=auth_header(token))
    assert resp.status_code == 422


async def test_parlay_without_legs_rejected(client: AsyncClient):
    token = await register_and_login(client, "nolegs", "nolegs@test.com")
    payload = sample_bet_payload(bet_type="PARLAY", legs=[])
    resp = await client.post("/bets", json=payload, headers=auth_header(token))
    assert resp.status_code == 422


async def test_parlay_leg_odds_validated(client: AsyncClient):
    token = await register_and_login(client, "badleg", "badleg@test.com")
    payload = sample_bet_payload(bet_type="PARLAY", legs=[_leg(odds=0.5)])
    resp = await client.post("/bets", json=payload, headers=auth_header(token))
    assert resp.status_code == 422


async def test_parlay_stats_use_combined_odds(client: AsyncClient):
    token = await register_and_login(client, "pstats", "pstats@test.com")
    h = auth_header(token)
    payload = sample_bet_payload(
        bet_type="PARLAY", odds=2.0, stake=10, legs=[_leg(sport="Tenis", odds=3.0)]
    )
    created = await client.post("/bets", json=payload, headers=h)
    bet_id = created.json()["id"]
    await client.put(f"/bets/{bet_id}", json={"status": "WON"}, headers=h)

    s = (await client.get("/statistics/me", headers=h)).json()
    assert s["net_profit"] == 50.0  # 10 * (6 - 1)
    assert s["won"] == 1
    # Deportes distintos = principal (Fútbol) + leg (Tenis).
    assert s["distinct_sports"] == 2
