"""Tests de integración de la gestión de apuestas."""

from httpx import AsyncClient

from tests.conftest import auth_header, register_and_login, sample_bet_payload


async def test_create_bet_computes_fields(client: AsyncClient):
    token = await register_and_login(client, "better", "better@test.com")
    resp = await client.post(
        "/bets", json=sample_bet_payload(odds=2.0, stake=10.0), headers=auth_header(token)
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["potential_return"] == 20.0
    assert data["potential_profit"] == 10.0
    assert data["implied_probability"] == 0.5
    assert data["created_at"]
    assert data["updated_at"]


async def test_create_bet_invalid_odds(client: AsyncClient):
    token = await register_and_login(client, "oddsuser", "odds@test.com")
    resp = await client.post("/bets", json=sample_bet_payload(odds=0.9), headers=auth_header(token))
    assert resp.status_code == 422


async def test_create_bet_invalid_stake(client: AsyncClient):
    token = await register_and_login(client, "stakeuser", "stake@test.com")
    resp = await client.post("/bets", json=sample_bet_payload(stake=0), headers=auth_header(token))
    assert resp.status_code == 422


async def test_create_bet_requires_auth(client: AsyncClient):
    resp = await client.post("/bets", json=sample_bet_payload())
    assert resp.status_code == 401


async def test_get_bet_by_id(client: AsyncClient):
    token = await register_and_login(client, "getuser", "get@test.com")
    created = await client.post("/bets", json=sample_bet_payload(), headers=auth_header(token))
    bet_id = created.json()["id"]
    resp = await client.get(f"/bets/{bet_id}", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["id"] == bet_id


async def test_list_bets_pagination_and_filter(client: AsyncClient):
    token = await register_and_login(client, "listuser", "list@test.com")
    for i in range(3):
        await client.post(
            "/bets",
            json=sample_bet_payload(sport="Tenis" if i == 0 else "Fútbol"),
            headers=auth_header(token),
        )

    # Paginación
    resp = await client.get("/bets?page=1&page_size=2", headers=auth_header(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2

    # Filtro por deporte
    resp = await client.get("/bets?sport=Tenis", headers=auth_header(token))
    assert resp.json()["total"] == 1


async def test_update_bet_recalculates(client: AsyncClient):
    token = await register_and_login(client, "upduser", "upd@test.com")
    created = await client.post(
        "/bets", json=sample_bet_payload(odds=2.0, stake=10.0), headers=auth_header(token)
    )
    bet_id = created.json()["id"]
    resp = await client.put(f"/bets/{bet_id}", json={"odds": 3.0}, headers=auth_header(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["odds"] == 3.0
    assert data["potential_return"] == 30.0
    assert data["potential_profit"] == 20.0


async def test_delete_bet(client: AsyncClient):
    token = await register_and_login(client, "deluser", "del@test.com")
    created = await client.post("/bets", json=sample_bet_payload(), headers=auth_header(token))
    bet_id = created.json()["id"]
    resp = await client.delete(f"/bets/{bet_id}", headers=auth_header(token))
    assert resp.status_code == 204
    resp = await client.get(f"/bets/{bet_id}", headers=auth_header(token))
    assert resp.status_code == 404


async def test_user_isolation(client: AsyncClient):
    token_a = await register_and_login(client, "usera", "usera@test.com")
    token_b = await register_and_login(client, "userb", "userb@test.com")

    created = await client.post("/bets", json=sample_bet_payload(), headers=auth_header(token_a))
    bet_id = created.json()["id"]

    # El usuario B no ve la apuesta de A.
    resp = await client.get(f"/bets/{bet_id}", headers=auth_header(token_b))
    assert resp.status_code == 404

    # Ni puede editarla ni eliminarla.
    resp = await client.put(f"/bets/{bet_id}", json={"odds": 5.0}, headers=auth_header(token_b))
    assert resp.status_code == 404

    # La lista de B está vacía.
    resp = await client.get("/bets", headers=auth_header(token_b))
    assert resp.json()["total"] == 0
