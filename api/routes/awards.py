"""
Award endpoints

GET /awards                              Search awards by name
GET /awards/{code}/classifications       Search classifications for an award
GET /awards/{code}/penalties             Get penalty rates for an award
GET /awards/{code}/allowances            Get allowances for an award
"""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query, HTTPException
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
    prefix="/awards",
    tags=["Awards"],
    dependencies=[Depends(verify_api_key)],
)


@router.get("", summary="Search awards by name")
@limiter.limit("60/minute")
def list_awards(
    request: Request,
    search: str = Query(..., min_length=2, max_length=100, description="Award name search term (typo-tolerant)"),
    top: int = Query(5, ge=1, le=20, description="Maximum results to return"),
):
    """
    Search for Awards by name. Handles partial matches and typos.
    Example: `search=retail` or `search=retial`
    """
    with get_cursor() as cur:
        results = search_awards(cur, search, top=top)
    if not results:
        raise HTTPException(status_code=404, detail="No awards found for that search term.")
    return results


@router.get("/{code}/classifications", summary="Search classifications for an award")
@limiter.limit("60/minute")
def list_classifications(
    request: Request,
    code: str,
    search: str = Query(..., min_length=1, max_length=100, description="Classification name or level keyword"),
    date: Optional[date] = Query(None, description="Point-in-time date (YYYY-MM-DD). Defaults to latest."),
    top: int = Query(5, ge=1, le=20),
):
    """
    Search classifications within an award, optionally filtered to a specific date.
    Returns hourly rates and weekly base rates for each match.
    """
    with get_cursor() as cur:
        results = search_classifications(cur, code, search, date, top=top)
    if not results:
        raise HTTPException(status_code=404, detail="No classifications found.")
    return results


@router.get("/{code}/penalties", summary="Get penalty rates for an award")
@limiter.limit("60/minute")
def list_penalties(
    request: Request,
    code: str,
    classification: str = Query("", max_length=200, description="Filter by classification name (optional)"),
    date: Optional[date] = Query(None, description="Point-in-time date (YYYY-MM-DD). Defaults to latest."),
):
    """
    Returns penalty multipliers (weekends, public holidays, overtime, night shift) for an award.
    If `classification` is provided, tries to narrow results to that classification first.
    """
    with get_cursor() as cur:
        results = get_penalties(cur, code, classification, date)
    return results


@router.get("/{code}/allowances", summary="Get allowances for an award")
@limiter.limit("60/minute")
def list_allowances(
    request: Request,
    code: str,
    date: Optional[date] = Query(None, description="Point-in-time date (YYYY-MM-DD). Defaults to latest."),
):
    """
    Returns all expense allowances (travel, meals, tools) and wage allowances
    (leading hand, etc.) for an award at the given date.
    """
    with get_cursor() as cur:
        expense = get_expense_allowances(cur, code, date)
        wage    = get_wage_allowances(cur, code, date)
    return {"expense_allowances": expense, "wage_allowances": wage}
