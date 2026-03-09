"""
Finder endpoint

GET /finder   Resolve search terms to a full Award data bundle
              (top award match + classification + penalties + allowances)
"""

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from starlette.requests import Request

from api.auth import verify_api_key
from api.db import get_cursor
from api.limiter import limiter
from finder.finder import (
    search_awards,
    search_classifications,
    get_penalties,
    get_expense_allowances,
    get_wage_allowances,
)

router = APIRouter(
    prefix="/finder",
    tags=["Finder"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", summary="Resolve search terms to full Award data")
@limiter.limit("30/minute")
def find(
    request: Request,
    award: str = Query(..., min_length=2, max_length=100, description="Award name search term"),
    classification: str = Query(..., min_length=1, max_length=100, description="Classification search term"),
    date: Optional[date] = Query(None, description="Point-in-time date (YYYY-MM-DD). Defaults to latest."),
    top: int = Query(3, ge=1, le=10, description="Number of alternative matches to include"),
    include_penalties: bool = Query(True, description="Include penalty rates in response"),
    include_allowances: bool = Query(True, description="Include allowances in response"),
):
    """
    One-shot resolver: finds the best matching Award and Classification for your
    search terms, then returns all associated penalties and allowances — ready
    for use in pay calculations.

    Handles typos: `award=retial` still resolves to the Retail Award.
    """
    with get_cursor() as cur:
        award_matches = search_awards(cur, award, top=top)
        if not award_matches:
            return {
                "resolved_at": datetime.now().isoformat(timespec="seconds"),
                "award": None,
                "classification": None,
                "penalties": [],
                "expense_allowances": [],
                "wage_allowances": [],
            }

        best_award = award_matches[0]
        class_matches = search_classifications(cur, best_award["award_code"], classification, date, top=top)
        best_class = class_matches[0] if class_matches else None

        penalties = []
        if include_penalties and best_class:
            penalties = get_penalties(cur, best_award["award_code"], best_class["classification"], date)

        expense_allowances = []
        wage_allowances = []
        if include_allowances:
            expense_allowances = get_expense_allowances(cur, best_award["award_code"], date)
            wage_allowances    = get_wage_allowances(cur, best_award["award_code"], date)

    return {
        "resolved_at":        datetime.now().isoformat(timespec="seconds"),
        "award":              {"top_match": best_award, "alternatives": award_matches[1:]},
        "classification":     {"top_match": best_class, "alternatives": class_matches[1:] if class_matches else []},
        "penalties":          penalties,
        "expense_allowances": expense_allowances,
        "wage_allowances":    wage_allowances,
    }
