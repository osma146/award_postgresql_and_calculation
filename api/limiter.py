"""
Shared rate limiter instance.
Imported by main.py (attached to app) and by each route module.
"""

from slowapi import Limiter
from starlette.requests import Request
from slowapi.util import get_remote_address


def _real_ip(request: Request) -> str:
    """Use Cloudflare's real IP header when available."""
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_real_ip)
