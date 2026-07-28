from fastapi import APIRouter

from app.api.v1 import portfolio, users

api_router = APIRouter()
# Both routers sit on the /users prefix: users owns the resource itself, portfolio
# the events derived from it. Nothing shadows anything today — every path is either
# one segment (/register, /active) or three (/{telegram_id}/...) — but a bare
# /users/{telegram_id} would swallow the static routes, so it has to go first.
api_router.include_router(users.router)
api_router.include_router(portfolio.router)
