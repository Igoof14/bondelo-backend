"""Bot users — the only table whose schema this service owns.

`bot_users` is migrated from here (see `migrations/`) and written to only by this
service. Other services (users_bonds, price-monitoring, rating-monitoring,
fns-monitoring, bondelo-reminders) read it directly.
"""

import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BotUser(Base):
    __tablename__ = "bot_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    # Read-only T-Invest token. Exposed by exactly one endpoint and never logged.
    tinvest_token: Mapped[str | None] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True)
    is_bot: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_activity: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
