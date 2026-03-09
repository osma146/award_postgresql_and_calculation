"""
Autocomplete endpoint — optimised for keystroke-by-keystroke search.

GET /autocomplete/awards?q=ret&top=10
GET /autocomplete/classifications?q=level+2&award=MA000004&top=10

Designed to be called on every keystroke from a search input.
Returns only the fields needed to populate a dropdown — fast and minimal.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from starlette.requests import Request

from api.auth import verify_api_key
from api.db import get_cursor
from api.limiter import limiter

router = APIRouter(
    prefix="/autocomplete",
    tags=["Autocomplete"],
    dependencies=[Depends(verify_api_key)],
)


def _search_awards_fast(cur, q: str, top: int) -> list[dict]:
    """
    Fast award name search tuned for partial/keystroke input.
    - Short queries (< 3 chars): prefix ILIKE only
    - Longer queries: prefix ILIKE + fuzzy word_similarity combined
    Results ranked by score descending.
    """
    q = q.strip()
    if not q:
        return []

    if len(q) < 3:
        # Short query — prefix match only, fast index scan
        cur.execute("""
            SELECT DISTINCT ON (award_code)
                award_code,
                name,
                1.0 AS score
            FROM awards
            WHERE name ILIKE %s
            ORDER BY award_code, name
            LIMIT %s
        """, (f"{q}%", top))
    else:
        # Longer query — prefix match + fuzzy, best score wins
        cur.execute("""
            SELECT award_code, name, score
            FROM (
                SELECT DISTINCT ON (award_code)
                    award_code,
                    name,
                    ROUND(
                        GREATEST(
                            CASE WHEN name ILIKE %s THEN 0.9 ELSE 0.0 END,
                            CASE WHEN name ILIKE %s THEN 0.8 ELSE 0.0 END,
                            word_similarity(%s, name)
                        )::numeric, 2
                    ) AS score
                FROM awards
                WHERE name ILIKE %s
                   OR name ILIKE %s
                   OR word_similarity(%s, name) > 0.25
                ORDER BY award_code, score DESC
            ) ranked
            ORDER BY score DESC
            LIMIT %s
        """, (
            f"{q}%",        # starts with — highest priority
            f"%{q}%",       # contains — medium priority
            q,              # fuzzy
            f"{q}%",        # WHERE starts with
            f"%{q}%",       # WHERE contains
            q,              # WHERE fuzzy
            top,
        ))

    rows = cur.fetchall()
    return [
        {"award_code": r[0], "name": r[1], "score": float(r[2])}
        for r in rows
    ]


def _search_classifications_fast(cur, award_code: str, q: str, top: int) -> list[dict]:
    """
    Fast classification search within an award, tuned for partial input.
    Returns classification name, level, and hourly rate only.
    """
    q = q.strip()
    if not q:
        return []

    if len(q) < 3:
        cur.execute("""
            SELECT DISTINCT ON (classification_fixed_id)
                classification_fixed_id,
                classification,
                classification_level,
                calculated_rate
            FROM classifications
            WHERE award_code = %s
              AND classification ILIKE %s
              AND classification IS NOT NULL
            ORDER BY classification_fixed_id, classification_level
            LIMIT %s
        """, (award_code, f"%{q}%", top))
    else:
        cur.execute("""
            SELECT classification_fixed_id, classification, classification_level, calculated_rate, score
            FROM (
                SELECT DISTINCT ON (classification_fixed_id)
                    classification_fixed_id,
                    classification,
                    classification_level,
                    calculated_rate,
                    ROUND(
                        GREATEST(
                            CASE WHEN classification ILIKE %s THEN 0.9 ELSE 0.0 END,
                            word_similarity(%s, COALESCE(classification, ''))
                        )::numeric, 2
                    ) AS score
                FROM classifications
                WHERE award_code = %s
                  AND (
                      classification ILIKE %s
                      OR word_similarity(%s, COALESCE(classification, '')) > 0.2
                  )
                  AND classification IS NOT NULL
                ORDER BY classification_fixed_id, score DESC
            ) ranked
            ORDER BY score DESC
            LIMIT %s
        """, (
            f"%{q}%", q,
            award_code,
            f"%{q}%", q,
            top,
        ))

    rows = cur.fetchall()
    return [
        {
            "classification_fixed_id": r[0],
            "classification":          r[1],
            "classification_level":    r[2],
            "calculated_rate_hourly":  float(r[3]) if r[3] is not None else None,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/awards", summary="Live award name autocomplete")
@limiter.limit("120/minute")
def autocomplete_awards(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100, description="Partial award name (1+ characters)"),
    top: int = Query(10, ge=1, le=20, description="Max results (default 10)"),
):
    """
    Typeahead search for award names. Call this on every keystroke.

    - 1–2 chars: prefix match (fast, low noise)
    - 3+ chars: prefix + fuzzy combined, ranked by closeness

    Returns `award_code` and `name` only — minimal payload for dropdowns.

    **Example:** `q=ret` → General Retail Industry Award, Retail Award 2010, …
    """
    with get_cursor() as cur:
        results = _search_awards_fast(cur, q, top)
    if not results:
        raise HTTPException(status_code=404, detail="No matches found.")
    return results


@router.get("/classifications", summary="Live classification autocomplete within an award")
@limiter.limit("120/minute")
def autocomplete_classifications(
    request: Request,
    award: str = Query(..., min_length=3, max_length=20, description="Award code (e.g. MA000004)"),
    q: str = Query(..., min_length=1, max_length=100, description="Partial classification name or level"),
    top: int = Query(10, ge=1, le=20),
):
    """
    Typeahead search for classification names within a specific award.
    Returns classification name, level, and hourly rate.

    **Typical flow:**
    1. User selects an award via `/autocomplete/awards`
    2. User types a classification — call this with the resolved `award_code`

    **Example:** `award=MA000004&q=level` → Level 1, Level 2, Level 3, …
    """
    with get_cursor() as cur:
        results = _search_classifications_fast(cur, award, q, top)
    if not results:
        raise HTTPException(status_code=404, detail="No classifications found.")
    return results
