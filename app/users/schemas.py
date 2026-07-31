from pydantic import BaseModel, Field, field_validator


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

    @field_validator("token")
    @classmethod
    def _usable_as_a_credential(cls, value: str) -> str:
        """Reject anything that cannot be sent as a bearer credential.

        Tokens arrive pasted into a chat, so they turn up wrapped in whitespace, and now
        and then with Cyrillic look-alikes or invisible characters in them. Both gRPC
        metadata and HTTP headers are ASCII-only: such a token used to crash the request
        with an encoding error deep inside the transport, which reached the user as a 500.

        The T-Invest token format itself is not checked — that is the broker's verdict to
        give, and hard-coding today's shape would break the day it changes.
        """
        token = value.strip()
        if not token:
            raise ValueError("must not be blank")
        if not (token.isascii() and token.isprintable()):
            raise ValueError("must contain printable ASCII characters only")
        return token


class TokenResponse(BaseModel):
    token: str | None = Field(default=None, repr=False)


class TokenStateResponse(BaseModel):
    has_token: bool
