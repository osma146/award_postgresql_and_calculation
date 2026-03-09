"""
API key authentication.

Every protected endpoint requires the header:
    X-API-Key: <your key>

The expected key is loaded from the API_KEY environment variable in .env.
"""

import os
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=True)


def verify_api_key(api_key: str = Security(_header_scheme)) -> str:
    expected = os.getenv("API_KEY", "")
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="API_KEY is not configured on this server.",
        )
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )
    return api_key
