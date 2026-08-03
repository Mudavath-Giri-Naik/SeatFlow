"""slowapi rate limiter, keyed by authenticated user when possible.

Falls back to remote IP for unauthenticated requests. Keying by user (not
just IP) matters here because many users can share an IP behind NAT/campus
wifi/office network, and we want the 10/min cap to apply per-user.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.security import InvalidTokenError, TokenType, decode_token


def rate_limit_key(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[len("bearer ") :]
        try:
            payload = decode_token(token, TokenType.ACCESS)
            return f"user:{payload['sub']}"
        except InvalidTokenError:
            pass
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=rate_limit_key)
