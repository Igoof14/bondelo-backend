from typing import Annotated

from fastapi import Depends, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session

DbSession = Annotated[AsyncSession, Depends(get_session)]

# Shared by every router under the /users prefix, so the description stays identical.
TelegramId = Annotated[int, Path(description="Telegram user id")]
