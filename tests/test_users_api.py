from http import HTTPStatus

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TELEGRAM_ID = 1825344258
UNKNOWN_ID = 999999


async def register(client: AsyncClient, telegram_id: int = TELEGRAM_ID, **fields: str) -> dict:
    response = await client.post(
        "/api/v1/users/register", json={"telegram_id": telegram_id, **fields}
    )
    assert response.status_code == HTTPStatus.OK
    return response.json()


async def test_register_creates_user(client: AsyncClient) -> None:
    assert await register(client, username="alice") == {
        "telegram_id": TELEGRAM_ID,
        "is_new_user": True,
        "has_token": False,
    }


async def test_register_is_idempotent(client: AsyncClient) -> None:
    await register(client)
    body = await register(client)
    assert body["is_new_user"] is False


async def test_register_reports_existing_token(client: AsyncClient) -> None:
    await register(client)
    await client.put(f"/api/v1/users/{TELEGRAM_ID}/token", json={"token": "t.secret"})

    body = await register(client)
    assert (body["is_new_user"], body["has_token"]) == (False, True)


async def test_register_reactivates_user(client: AsyncClient) -> None:
    await register(client)
    await client.post(f"/api/v1/users/{TELEGRAM_ID}/deactivate")

    await register(client)

    active = await client.get("/api/v1/users/active")
    assert active.json()["telegram_ids"] == [TELEGRAM_ID]


async def test_empty_token_counts_as_no_token(client: AsyncClient, session: AsyncSession) -> None:
    """The token used to be cleared with an empty string, not NULL — it means "no token"."""
    await register(client)
    await session.execute(text("UPDATE bot_users SET tinvest_token = ''"))
    await session.commit()

    body = await register(client)
    assert body["has_token"] is False

    response = await client.get(f"/api/v1/users/{TELEGRAM_ID}/token")
    assert response.json() == {"token": None}


async def test_token_lifecycle(client: AsyncClient) -> None:
    await register(client)

    assert (await client.get(f"/api/v1/users/{TELEGRAM_ID}/token")).json() == {"token": None}

    put = await client.put(f"/api/v1/users/{TELEGRAM_ID}/token", json={"token": "t.secret"})
    assert put.status_code == HTTPStatus.OK
    assert put.json() == {"has_token": True}

    get = await client.get(f"/api/v1/users/{TELEGRAM_ID}/token")
    assert get.json() == {"token": "t.secret"}

    delete = await client.delete(f"/api/v1/users/{TELEGRAM_ID}/token")
    assert delete.status_code == HTTPStatus.NO_CONTENT
    assert (await client.get(f"/api/v1/users/{TELEGRAM_ID}/token")).json() == {"token": None}


async def test_empty_token_is_rejected(client: AsyncClient) -> None:
    await register(client)
    response = await client.put(f"/api/v1/users/{TELEGRAM_ID}/token", json={"token": ""})
    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_unknown_user_is_404(client: AsyncClient) -> None:
    for method, url in (
        ("GET", f"/api/v1/users/{UNKNOWN_ID}/token"),
        ("PUT", f"/api/v1/users/{UNKNOWN_ID}/token"),
        ("DELETE", f"/api/v1/users/{UNKNOWN_ID}/token"),
        ("POST", f"/api/v1/users/{UNKNOWN_ID}/deactivate"),
    ):
        response = await client.request(method, url, json={"token": "t.secret"})
        assert response.status_code == HTTPStatus.NOT_FOUND, url
        assert response.json()["code"] == "not_found"


async def test_active_users_excludes_deactivated(client: AsyncClient) -> None:
    await register(client, telegram_id=1)
    await register(client, telegram_id=2)

    response = await client.post("/api/v1/users/2/deactivate")
    assert response.status_code == HTTPStatus.NO_CONTENT

    assert (await client.get("/api/v1/users/active")).json() == {"telegram_ids": [1], "count": 1}


async def test_active_resolves_as_a_static_route(client: AsyncClient) -> None:
    """`/users/active` reaches its own handler and is not read as a telegram id.

    Nothing shadows it today — every other path under /users has a different segment
    count — so this guards a future `GET /users/{telegram_id}` declared ahead of it.
    """
    response = await client.get("/api/v1/users/active")
    assert response.status_code == HTTPStatus.OK
    assert response.json() == {"telegram_ids": [], "count": 0}
