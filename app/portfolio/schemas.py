import datetime
from decimal import Decimal

from pydantic import BaseModel


class AccountPosition(BaseModel):
    broker: str
    account_id: str
    account_name: str | None = None
    quantity: Decimal


class BondInfo(BaseModel):
    secid: str
    isin: str | None = None
    shortname: str | None = None
    name: str | None = None
    facevalue: Decimal | None = None
    faceunit: str | None = None
    matdate: datetime.date | None = None


class OfferInfo(BaseModel):
    date: datetime.date
    type: str
    date_start: datetime.date | None = None
    date_end: datetime.date | None = None
    price: Decimal | None = None
    value: Decimal | None = None
    agent: str | None = None
    days_left: int


class OfferItem(BaseModel):
    bond: BondInfo
    offer: OfferInfo
    quantity: Decimal
    accounts: list[AccountPosition]


class UpcomingOffersResponse(BaseModel):
    telegram_id: int
    items: list[OfferItem]
