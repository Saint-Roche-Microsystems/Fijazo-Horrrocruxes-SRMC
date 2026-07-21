"""Tests de integración de autenticación."""

from httpx import AsyncClient

from tests.conftest import auth_header, register_and_login


async def test_register_ok(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"username": "carlos", "email": "carlos@test.com", "password": "password123"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "carlos"
    assert data["email"] == "carlos@test.com"
    assert data["role"] == "USER"
    assert "id" in data
    assert "password" not in data


async def test_register_duplicate_email(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "user1", "email": "dup@test.com", "password": "password123"},
    )
    resp = await client.post(
        "/auth/register",
        json={"username": "user2", "email": "dup@test.com", "password": "password123"},
    )
    assert resp.status_code == 409


async def test_register_duplicate_username(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "same", "email": "a@test.com", "password": "password123"},
    )
    resp = await client.post(
        "/auth/register",
        json={"username": "same", "email": "b@test.com", "password": "password123"},
    )
    assert resp.status_code == 409


async def test_register_invalid_username_length(client: AsyncClient):
    resp = await client.post(
        "/auth/register",
        json={"username": "ab", "email": "x@test.com", "password": "password123"},
    )
    assert resp.status_code == 422


async def test_login_ok(client: AsyncClient):
    token = await register_and_login(client, "loginuser", "login@test.com")
    assert token


async def test_login_invalid_credentials(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "creduser", "email": "cred@test.com", "password": "password123"},
    )
    resp = await client.post(
        "/auth/login", json={"email": "cred@test.com", "password": "wrongpass1"}
    )
    assert resp.status_code == 401


async def test_login_locks_after_max_attempts(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "lockuser", "email": "lock@test.com", "password": "password123"},
    )

    # login_max_attempts por defecto es 5: las 4 primeras fallan como credenciales
    # inválidas normales; la 5ª dispara el bloqueo.
    for _ in range(4):
        resp = await client.post(
            "/auth/login", json={"email": "lock@test.com", "password": "wrongpass1"}
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/auth/login", json={"email": "lock@test.com", "password": "wrongpass1"}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers

    # Bloqueada incluso con la contraseña correcta.
    resp = await client.post(
        "/auth/login", json={"email": "lock@test.com", "password": "password123"}
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


async def test_login_success_resets_failed_attempts(client: AsyncClient):
    await client.post(
        "/auth/register",
        json={"username": "resetuser", "email": "reset@test.com", "password": "password123"},
    )

    for _ in range(3):
        resp = await client.post(
            "/auth/login", json={"email": "reset@test.com", "password": "wrongpass1"}
        )
        assert resp.status_code == 401

    resp = await client.post(
        "/auth/login", json={"email": "reset@test.com", "password": "password123"}
    )
    assert resp.status_code == 200

    # Tras el login exitoso el contador se resetea: 3 fallos más no bloquean.
    for _ in range(3):
        resp = await client.post(
            "/auth/login", json={"email": "reset@test.com", "password": "wrongpass1"}
        )
        assert resp.status_code == 401


async def test_me_requires_token(client: AsyncClient):
    resp = await client.get("/users/me")
    assert resp.status_code == 401


async def test_me_ok(client: AsyncClient):
    token = await register_and_login(client, "meuser", "me@test.com")
    resp = await client.get("/users/me", headers=auth_header(token))
    assert resp.status_code == 200
    assert resp.json()["email"] == "me@test.com"
