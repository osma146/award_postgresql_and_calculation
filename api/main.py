"""
Australian Awards API

Run locally:
    uvicorn api.main:app --reload --port 8000

Interactive docs:
    http://localhost:8000/docs
"""

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from dotenv import load_dotenv

from api.limiter import limiter
from api.routes import health, awards, finder, payslips, autocomplete

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Australian Awards API",
    description=(
        "Point-in-time Award rate lookups, fuzzy search, and payslip compliance auditing "
        "for Australian Modern Awards (Fair Work Commission data, 2015–present)."
    ),
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# ---------------------------------------------------------------------------
# CORS — restrict to your domain(s) via ALLOWED_ORIGINS in .env
# Example: ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
# ---------------------------------------------------------------------------

_origins = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(health.router)
app.include_router(awards.router)
app.include_router(finder.router)
app.include_router(payslips.router)
app.include_router(autocomplete.router)
