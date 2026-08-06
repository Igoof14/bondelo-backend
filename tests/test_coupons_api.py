"""Coupons paid today for the user's portfolio, with the issuer disclosure status.

The tables these queries read (`user_bonds`, `moex_bonds*`, `disclosure_payments`)
belong to other services; `conftest.py` creates their shape for the test database.
"""

import datetime
from http import HTTPStatus

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TELEGRAM_ID = 1825344258
OTHER_TELEGRAM_ID = 1825344259
UNKNOWN_ID = 999999

TODAY = datetime.date.today()


async def _register(client: AsyncClient, telegram_id: int = TELEGRAM_ID) -> None:
    response = await client.post("/api/v1/users/register", json={"telegram_id": telegram_id})
    assert response.status_code == HTTPStatus.OK


async def _add_bond(
    session: AsyncSession,
    *,
    secid: str,
    isin: str,
    telegram_id: int = TELEGRAM_ID,
    quantity: str = "10",
    value_rub: str | None = "31.25",
    coupondate: datetime.date = TODAY,
) -> None:
    """A MOEX bond with a coupon on `coupondate`, held by the given user."""
    await session.execute(
        text("""
            INSERT INTO moex_bonds (secid, shortname, name, isin, facevalue, faceunit, matdate)
            VALUES (:secid, :secid, :secid || ' bond', :isin, 1000, 'SUR', :matdate)
            ON CONFLICT (secid) DO NOTHING
        """),
        {"secid": secid, "isin": isin, "matdate": TODAY + datetime.timedelta(days=365)},
    )
    await session.execute(
        text("""
            INSERT INTO moex_bonds_coupons (secid, coupondate, startdate, value_rub)
            VALUES (:secid, :coupondate, :startdate, :value_rub)
        """),
        {
            "secid": secid,
            "coupondate": coupondate,
            "startdate": coupondate - datetime.timedelta(days=91),
            "value_rub": value_rub,
        },
    )
    await session.execute(
        text("""
            INSERT INTO user_bonds (bot_user_id, broker, account_id, account_name, isin, quantity)
            SELECT id, 'tinkoff', 'acc-1', 'Main', :isin, :quantity
            FROM bot_users WHERE telegram_id = :telegram_id
        """),
        {"isin": isin, "quantity": quantity, "telegram_id": telegram_id},
    )
    await session.commit()


async def _add_disclosure(
    session: AsyncSession,
    *,
    isin: str,
    due_date: datetime.date = TODAY,
    category: str = "coupon_income",
    event_date: datetime.date | None = None,
    per_security: float = 31.25,
    url: str = "https://e-disclosure.ru/event/1",
) -> None:
    await session.execute(
        text("""
            INSERT INTO disclosure_payments (
                isin, payment_category, obligation_due_date, total_payment_amount,
                payment_per_security_value, event_url, event_date
            )
            VALUES (
                :isin, CAST(:category AS payment_category_enum), :due_date, 312500,
                :per_security, :url, :event_date
            )
        """),
        {
            "isin": isin,
            "category": category,
            "due_date": due_date,
            "per_security": per_security,
            "url": url,
            "event_date": event_date,
        },
    )
    await session.commit()


async def _coupons(client: AsyncClient, telegram_id: int = TELEGRAM_ID, **params: str) -> dict:
    response = await client.get(f"/api/v1/users/{telegram_id}/coupons", params=params)
    assert response.status_code == HTTPStatus.OK
    return response.json()


async def test_coupon_with_disclosure(client: AsyncClient, session: AsyncSession) -> None:
    await _register(client)
    await _add_bond(session, secid="SU001", isin="RU000A100001")
    await _add_disclosure(session, isin="RU000A100001")

    body = await _coupons(client)

    assert body["telegram_id"] == TELEGRAM_ID
    assert body["date"] == TODAY.isoformat()
    (item,) = body["items"]
    assert item["bond"]["isin"] == "RU000A100001"
    assert item["coupon"] == {
        "date": TODAY.isoformat(),
        "start_date": (TODAY - datetime.timedelta(days=91)).isoformat(),
        "value_rub": "31.25",
    }
    assert (item["quantity"], item["total_value_rub"]) == ("10.0000", "312.500000")
    assert item["is_disclosure"] is True
    assert item["disclosure"] == {
        "total_payment_amount": 312500.0,
        "payment_per_security_value": 31.25,
        "event_url": "https://e-disclosure.ru/event/1",
    }
    assert item["nsd"] == {"is_paid": False, "url": None}
    assert item["accounts"] == [
        {"broker": "tinkoff", "account_id": "acc-1", "account_name": "Main", "quantity": "10.0000"}
    ]


async def test_coupon_without_disclosure(client: AsyncClient, session: AsyncSession) -> None:
    await _register(client)
    await _add_bond(session, secid="SU001", isin="RU000A100001")

    (item,) = (await _coupons(client))["items"]

    assert (item["is_disclosure"], item["disclosure"]) == (False, None)


async def test_disclosure_of_another_kind_or_date_is_ignored(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _register(client)
    await _add_bond(session, secid="SU001", isin="RU000A100001")
    await _add_disclosure(session, isin="RU000A100001", category="amortization")
    await _add_disclosure(session, isin="RU000A100001", due_date=TODAY + datetime.timedelta(days=1))

    (item,) = (await _coupons(client))["items"]

    assert item["is_disclosure"] is False


async def test_repeated_disclosures_do_not_duplicate_the_coupon(
    client: AsyncClient, session: AsyncSession
) -> None:
    """An issuer can re-publish the same payment; the newest message wins."""
    await _register(client)
    await _add_bond(session, secid="SU001", isin="RU000A100001")
    await _add_disclosure(
        session,
        isin="RU000A100001",
        event_date=TODAY - datetime.timedelta(days=3),
        url="https://e-disclosure.ru/event/old",
    )
    await _add_disclosure(
        session,
        isin="RU000A100001",
        event_date=TODAY - datetime.timedelta(days=1),
        url="https://e-disclosure.ru/event/new",
    )

    (item,) = (await _coupons(client))["items"]

    assert item["disclosure"]["event_url"] == "https://e-disclosure.ru/event/new"


async def test_coupons_of_other_days_and_other_users_are_excluded(
    client: AsyncClient, session: AsyncSession
) -> None:
    await _register(client)
    await _register(client, OTHER_TELEGRAM_ID)
    await _add_bond(session, secid="SU001", isin="RU000A100001")
    await _add_bond(
        session, secid="SU002", isin="RU000A100002", coupondate=TODAY + datetime.timedelta(days=1)
    )
    await _add_bond(session, secid="SU003", isin="RU000A100003", telegram_id=OTHER_TELEGRAM_ID)

    items = (await _coupons(client))["items"]

    assert [i["bond"]["secid"] for i in items] == ["SU001"]


async def test_date_parameter_selects_another_day(
    client: AsyncClient, session: AsyncSession
) -> None:
    tomorrow = TODAY + datetime.timedelta(days=1)
    await _register(client)
    await _add_bond(session, secid="SU002", isin="RU000A100002", coupondate=tomorrow)
    await _add_disclosure(session, isin="RU000A100002", due_date=tomorrow)

    body = await _coupons(client, date=tomorrow.isoformat())

    assert body["date"] == tomorrow.isoformat()
    (item,) = body["items"]
    assert (item["bond"]["secid"], item["is_disclosure"]) == ("SU002", True)


async def test_no_coupons_today_is_an_empty_list(client: AsyncClient) -> None:
    await _register(client)

    assert (await _coupons(client))["items"] == []


async def test_unknown_user_is_not_found(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/users/{UNKNOWN_ID}/coupons")

    assert response.status_code == HTTPStatus.NOT_FOUND
    assert response.json()["code"] == "not_found"
