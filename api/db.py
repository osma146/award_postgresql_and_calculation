"""
Database connection for the API.
Opens a new connection per request and closes it when done.
"""

import os
from contextlib import contextmanager
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")


def _params() -> dict:
    return dict(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "awards_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


@contextmanager
def get_cursor():
    conn = psycopg2.connect(**_params())
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()
