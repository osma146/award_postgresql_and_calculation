"""
GET /health — public endpoint, no auth required.
Used by Cloudflare health checks and monitoring.
"""

from fastapi import APIRouter
from api.db import get_cursor

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Health check")
def health_check():
    """Returns API and database status. No authentication required."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1")
        db = "connected"
    except Exception as exc:
        db = f"error: {exc}"

    return {"status": "ok", "db": db}
