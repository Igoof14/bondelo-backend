from http import HTTPStatus

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TELEGRAM_ID = 1825344258
BASE = f"/api/v1/users/{TELEGRAM_ID}/notifications"


async def get_settings(client: AsyncClient) -> dict:
    response = await client.get(BASE)
    assert response.status_code == HTTPStatus.OK
    return response.json()


async def toggle(client: AsyncClient, path: str) -> bool:
    response = await client.post(f"{BASE}/{path}/toggle")
    assert response.status_code == HTTPStatus.OK
    return response.json()["alerts_enabled"]


async def test_untouched_user_reads_defaults(client: AsyncClient) -> None:
    body = await get_settings(client)

    assert body["telegram_id"] == TELEGRAM_ID
    assert body["offers"] == {
        "alerts_enabled": False,
        "first_alert": 14,
        "second_alert": 5,
        "notification_time": "10:00:00",
    }
    assert body["prices"]["drop_warning_threshold"] == 2.0
    assert body["ratings"] == {"enabled_agencies": []}
    assert body["fns"] == {"alerts_enabled": False}


async def test_reading_creates_no_rows(client: AsyncClient, session: AsyncSession) -> None:
    """A hub render must not write: an absent row is what "off" means downstream."""
    await get_settings(client)

    for table in ("offer_alert_settings", "price_alert_settings", "fns_alert_settings"):
        count = await session.scalar(text(f"SELECT count(*) FROM {table}"))
        assert count == 0, table


@pytest.mark.parametrize(
    ("path", "section"), [("offers", "offers"), ("prices", "prices"), ("fns", "fns")]
)
async def test_toggle_flips_state(client: AsyncClient, path: str, section: str) -> None:
    assert await toggle(client, path) is True
    assert (await get_settings(client))[section]["alerts_enabled"] is True

    assert await toggle(client, path) is False
    assert (await get_settings(client))[section]["alerts_enabled"] is False


async def test_update_offers_is_partial(client: AsyncClient) -> None:
    response = await client.patch(f"{BASE}/offers", json={"first_alert": 20})
    assert response.status_code == HTTPStatus.OK

    body = response.json()
    assert body["first_alert"] == 20
    # Untouched fields keep their defaults rather than being reset.
    assert body["second_alert"] == 5
    assert body["notification_time"] == "10:00:00"


async def test_update_offers_keeps_enabled_flag(client: AsyncClient) -> None:
    """Editing settings must not silently switch the alerts off."""
    await toggle(client, "offers")

    await client.patch(f"{BASE}/offers", json={"notification_time": "09:30:00"})

    offers = (await get_settings(client))["offers"]
    assert offers["alerts_enabled"] is True
    assert offers["notification_time"] == "09:30:00"


async def test_update_prices_thresholds(client: AsyncClient) -> None:
    response = await client.patch(f"{BASE}/prices", json={"drop_critical_threshold": 8.5})

    assert response.json()["drop_critical_threshold"] == 8.5
    assert response.json()["rise_warning_threshold"] == 3.0


@pytest.mark.parametrize("value", [0, 100, -1])
async def test_threshold_out_of_range_is_rejected(client: AsyncClient, value: float) -> None:
    response = await client.patch(f"{BASE}/prices", json={"drop_warning_threshold": value})

    assert response.status_code == HTTPStatus.UNPROCESSABLE_ENTITY


async def test_empty_update_returns_current_state(client: AsyncClient) -> None:
    await client.patch(f"{BASE}/offers", json={"first_alert": 30})

    response = await client.patch(f"{BASE}/offers", json={})

    assert response.status_code == HTTPStatus.OK
    assert response.json()["first_alert"] == 30


async def test_rating_agencies_toggle_independently(client: AsyncClient) -> None:
    assert await toggle(client, "ratings/nra") is True
    assert (await get_settings(client))["ratings"]["enabled_agencies"] == ["nra"]

    assert await toggle(client, "ratings/nkr") is True
    assert (await get_settings(client))["ratings"]["enabled_agencies"] == ["nkr", "nra"]

    assert await toggle(client, "ratings/nra") is False
    assert (await get_settings(client))["ratings"]["enabled_agencies"] == ["nkr"]


async def test_sections_do_not_interfere(client: AsyncClient) -> None:
    await toggle(client, "prices")

    body = await get_settings(client)
    assert body["prices"]["alerts_enabled"] is True
    assert body["offers"]["alerts_enabled"] is False
    assert body["fns"]["alerts_enabled"] is False
