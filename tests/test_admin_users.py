"""Tests de administración de usuarios (solo ADMIN)."""

from httpx import AsyncClient

from tests.conftest import auth_header, register_and_login


async def _make_admin(client: AsyncClient, test_db, username: str, email: str) -> dict:
    """Registra un usuario, lo promociona a ADMIN en la BD y devuelve su header."""

    token = await register_and_login(client, username, email)
    await test_db["users"].update_one({"email": email}, {"$set": {"role": "ADMIN"}})
    return auth_header(token)


async def _user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/users/me", headers=headers)).json()["id"]


async def test_list_users_requires_admin(client: AsyncClient):
    token = await register_and_login(client, "normal", "normal@test.com")
    resp = await client.get("/users", headers=auth_header(token))
    assert resp.status_code == 403


async def test_admin_lists_users(client: AsyncClient, test_db):
    admin_h = await _make_admin(client, test_db, "admin1", "admin1@test.com")
    await register_and_login(client, "member", "member@test.com")

    resp = await client.get("/users?page=1&page_size=10", headers=admin_h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    emails = {u["email"] for u in body["items"]}
    assert {"admin1@test.com", "member@test.com"} == emails
    assert all("active" in u for u in body["items"])


async def test_deactivate_blocks_login_and_token(client: AsyncClient, test_db):
    admin_h = await _make_admin(client, test_db, "admin2", "admin2@test.com")
    member_token = await register_and_login(client, "victim", "victim@test.com")
    member_h = auth_header(member_token)
    member_id = await _user_id(client, member_h)

    # El token del miembro funciona antes de desactivar.
    assert (await client.get("/users/me", headers=member_h)).status_code == 200

    resp = await client.patch(f"/users/{member_id}/active", json={"active": False}, headers=admin_h)
    assert resp.status_code == 200
    assert resp.json()["active"] is False

    # Login bloqueado y token invalidado (403).
    login = await client.post(
        "/auth/login", json={"email": "victim@test.com", "password": "password123"}
    )
    assert login.status_code == 403
    assert (await client.get("/users/me", headers=member_h)).status_code == 403


async def test_admin_cannot_deactivate_self(client: AsyncClient, test_db):
    admin_h = await _make_admin(client, test_db, "admin3", "admin3@test.com")
    admin_id = await _user_id(client, admin_h)
    resp = await client.patch(f"/users/{admin_id}/active", json={"active": False}, headers=admin_h)
    assert resp.status_code == 403
