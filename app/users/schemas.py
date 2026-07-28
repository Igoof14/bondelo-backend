from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class RegisterResponse(BaseModel):
    telegram_id: int
    is_new_user: bool
    has_token: bool


class ActiveUsersResponse(BaseModel):
    telegram_ids: list[int]
    count: int


class TokenRequest(BaseModel):
    # repr=False keeps the token out of tracebacks and validation error messages.
    token: str = Field(min_length=1, max_length=255, repr=False)


class TokenResponse(BaseModel):
    token: str | None = Field(default=None, repr=False)


class TokenStateResponse(BaseModel):
    has_token: bool
