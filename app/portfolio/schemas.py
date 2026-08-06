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


class MaturityInfo(BaseModel):
    date: datetime.date
    days_left: int


class MaturityItem(BaseModel):
    bond: BondInfo
    maturity: MaturityInfo
    quantity: Decimal
    accounts: list[AccountPosition]


class UpcomingMaturitiesResponse(BaseModel):
    telegram_id: int
    items: list[MaturityItem]


class CouponInfo(BaseModel):
    date: datetime.date
    start_date: datetime.date | None = None
    value_rub: Decimal | None = None


class DisclosureInfo(BaseModel):
    """What the issuer published about this payment. Amounts are floats in the source table."""

    total_payment_amount: float
    payment_per_security_value: float | None = None
    event_url: str | None = None


class NsdInfo(BaseModel):
    """Whether the money reached NSD. Not collected yet — the defaults are a placeholder."""

    is_paid: bool = False
    url: str | None = None


class CouponPaymentItem(BaseModel):
    bond: BondInfo
    coupon: CouponInfo
    quantity: Decimal
    total_value_rub: Decimal | None = None
    is_disclosure: bool
    disclosure: DisclosureInfo | None = None
    nsd: NsdInfo
    accounts: list[AccountPosition]


class CouponPaymentsResponse(BaseModel):
    telegram_id: int
    date: datetime.date
    items: list[CouponPaymentItem]
