"""
Payslip endpoint

POST /payslips/check   Submit a payslip JSON and receive the audit result
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Body
from starlette.requests import Request

from api.auth import verify_api_key
from api.limiter import limiter
from payslips.checker import check_payslip

router = APIRouter(
    prefix="/payslips",
    tags=["Payslips"],
    dependencies=[Depends(verify_api_key)],
)


@router.post("/check", summary="Audit a payslip for overpay / underpay")
@limiter.limit("30/minute")
def check(
    request: Request,
    payslip: Any = Body(..., description="Full payslip JSON object"),
):
    """
    Submit a payslip JSON body and receive a compliance audit result.

    Returns:
    - `calculated_gross` — what the employee should have been paid
    - `paid_gross` — what was actually paid
    - `variance` — difference in dollars
    - `variance_pct` — percentage difference
    - `status` — `correct`, `underpaid`, or `overpaid`
    - `issues` — list of specific problems found
    """
    if not isinstance(payslip, dict):
        raise HTTPException(status_code=422, detail="Request body must be a JSON object.")

    required = {"payslip_id", "employee", "pay_period", "audit"}
    missing = required - payslip.keys()
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required payslip fields: {sorted(missing)}",
        )

    try:
        return check_payslip(payslip, verbose=False)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing payslip field: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Audit error: {exc}")
