"""Read-only mappings of tables owned by other services.

These tables are created and migrated elsewhere (users_bonds, MOEX importers). This
service never writes to them — only the columns it reads are mapped. The one table it
does own, `bot_users`, lives in `app/users/models.py`.
"""

import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.users.models import BotUser

__all__ = ["BotUser", "MoexBond", "MoexBondOffer", "UserBond"]


class UserBond(Base):
    __tablename__ = "user_bonds"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    bot_user_id: Mapped[int]
    broker: Mapped[str] = mapped_column(String(50))
    account_id: Mapped[str] = mapped_column(String(255))
    account_name: Mapped[str | None] = mapped_column(String(255))
    figi: Mapped[str | None] = mapped_column(String(64))
    isin: Mapped[str | None] = mapped_column(String(32))
    ticker: Mapped[str | None] = mapped_column(String(64))
    quantity: Mapped[Decimal] = mapped_column(Numeric(19, 4))


class MoexBond(Base):
    __tablename__ = "moex_bonds"

    secid: Mapped[str] = mapped_column(Text, primary_key=True)
    isin: Mapped[str | None] = mapped_column(Text)
    shortname: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    facevalue: Mapped[Decimal | None] = mapped_column(Numeric)
    faceunit: Mapped[str | None] = mapped_column(Text)
    matdate: Mapped[datetime.date | None] = mapped_column(Date)


class MoexBondOffer(Base):
    __tablename__ = "moex_bonds_offers"

    secid: Mapped[str] = mapped_column(Text, primary_key=True)
    offerdate: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
    offertype: Mapped[str] = mapped_column(Text, primary_key=True)
    offerdatestart: Mapped[datetime.date | None] = mapped_column(Date)
    offerdateend: Mapped[datetime.date | None] = mapped_column(Date)
    price: Mapped[Decimal | None] = mapped_column(Numeric)
    value: Mapped[Decimal | None] = mapped_column(Numeric)
    agent: Mapped[str | None] = mapped_column(Text)
