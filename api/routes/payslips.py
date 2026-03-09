"""
Payslip endpoints

POST /payslips/generate  Generate a payslip from shift data using live DB rates
POST /payslips/check     Audit an existing payslip JSON for overpay / underpay
"""

from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel, Field
from starlette.requests import Request

from api.auth import verify_api_key
from api.db import get_cursor
from api.limiter import limiter
from payslips.checker import check_payslip

router = APIRouter(
    prefix="/payslips",
    tags=["Payslips"],
    dependencies=[Depends(verify_api_key)],
)

# Penalty multipliers — standard Modern Award values
_PENALTY = {
    "weekday_ordinary": 1.00,
    "saturday":         1.50,
    "sunday":           2.00,
    "public_holiday":   2.25,
    "overtime_t1":      1.50,
    "overtime_t2":      2.00,
}

# ---------------------------------------------------------------------------
# Pydantic models for /generate
# ---------------------------------------------------------------------------

class ShiftItem(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    day_type: str = Field(..., description="weekday_ordinary | saturday | sunday | public_holiday")
    hours_worked: float = Field(..., gt=0, le=24)
    overtime_hours: float = Field(0.0, ge=0)
    allowances: list[dict] = Field(default_factory=list,
                                   description='[{"name": "...", "amount": 17.03, "unit": "per_shift"}]')


class EmployeeInfo(BaseModel):
    name: str
    employment_type: Literal["full_time", "part_time", "casual"]
    classification_level: int = Field(..., ge=1, le=20)


class PayPeriod(BaseModel):
    start: str = Field(..., description="YYYY-MM-DD")
    end: str   = Field(..., description="YYYY-MM-DD")
    type: Literal["weekly", "fortnightly", "monthly"] = "fortnightly"


class GeneratePayslipRequest(BaseModel):
    payslip_id: str = Field(..., description="Unique payslip reference (e.g. PS-2024-005)")
    award_code: str = Field(..., min_length=3, max_length=20)
    employee: EmployeeInfo
    pay_period: PayPeriod
    shifts: list[ShiftItem] = Field(..., min_length=1, max_length=100)
    paid_gross: float = Field(..., ge=0, description="What was actually paid")
    paid_notes: str = Field("", description="Optional note explaining any discrepancy")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_rate(cur, award_code: str, level: int, lookup_date: str) -> float:
    cur.execute("""
        SELECT calculated_rate
        FROM classifications
        WHERE award_code = %s
          AND classification_level = %s
          AND operative_from <= %s
          AND (operative_to >= %s OR operative_to IS NULL)
          AND calculated_rate IS NOT NULL
        ORDER BY operative_from DESC
        LIMIT 1
    """, (award_code, level, lookup_date, lookup_date))
    row = cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No rate found for award '{award_code}', level {level}, date {lookup_date}.",
        )
    return float(row[0])


def _get_award_name(cur, award_code: str) -> str:
    cur.execute("SELECT name FROM awards WHERE award_code = %s LIMIT 1", (award_code,))
    row = cur.fetchone()
    return row[0] if row else award_code


def _calc_shift(base_rate: float, shift: ShiftItem) -> dict:
    ordinary_hours = max(shift.hours_worked - shift.overtime_hours, 0.0)
    multiplier     = _PENALTY.get(shift.day_type, 1.0)
    ordinary_pay   = round(ordinary_hours * base_rate * multiplier, 2)

    ot_t1        = min(shift.overtime_hours, 2.0)
    ot_t2        = max(shift.overtime_hours - 2.0, 0.0)
    overtime_pay = round(ot_t1 * base_rate * _PENALTY["overtime_t1"] +
                         ot_t2 * base_rate * _PENALTY["overtime_t2"], 2)

    allowance_total = round(sum(a.get("amount", 0) for a in shift.allowances), 2)

    return {
        "date":              shift.date,
        "day_type":          shift.day_type,
        "penalty_applied":   f"{multiplier * 100:.0f}%",
        "hours_worked":      shift.hours_worked,
        "overtime_hours":    shift.overtime_hours,
        "ordinary_pay":      ordinary_pay,
        "overtime_pay":      overtime_pay,
        "allowances_detail": shift.allowances,
        "allowances_total":  allowance_total,
        "shift_gross":       round(ordinary_pay + overtime_pay + allowance_total, 2),
    }


def _audit(calculated_gross: float, paid_gross: float, issues: list) -> dict:
    variance = round(paid_gross - calculated_gross, 2)
    if abs(variance) < 0.01:
        status = "correct"
    elif variance < 0:
        status = "underpaid"
    else:
        status = "overpaid"
    return {
        "calculated_gross": calculated_gross,
        "paid_gross":        paid_gross,
        "variance":          variance,
        "variance_pct":      round((variance / calculated_gross) * 100, 2) if calculated_gross else 0,
        "status":            status,
        "issues":            issues,
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/generate", summary="Generate a payslip from shift data")
@limiter.limit("30/minute")
def generate(request: Request, body: GeneratePayslipRequest):
    """
    Generate a full payslip JSON from shift inputs using live Award rates from the database.

    Looks up the correct hourly rate for the employee's award and classification level,
    calculates gross pay for each shift (with penalties and allowances), then compares
    the calculated total against `paid_gross` to produce an audit result.

    **Returns a complete payslip JSON** including:
    - Per-shift breakdowns with penalties applied
    - Calculated totals
    - Paid amount
    - Audit result: `correct`, `underpaid`, or `overpaid`
    """
    lookup_date = body.pay_period.start

    with get_cursor() as cur:
        rate       = _get_rate(cur, body.award_code, body.employee.classification_level, lookup_date)
        award_name = _get_award_name(cur, body.award_code)

    shift_calcs = [_calc_shift(rate, s) for s in body.shifts]

    totals = {
        "total_ordinary_pay": round(sum(s["ordinary_pay"]    for s in shift_calcs), 2),
        "total_overtime_pay": round(sum(s["overtime_pay"]    for s in shift_calcs), 2),
        "total_allowances":   round(sum(s["allowances_total"] for s in shift_calcs), 2),
        "gross_pay":          round(sum(s["shift_gross"]      for s in shift_calcs), 2),
    }

    # Auto-detect issues based on variance
    issues = []
    variance = round(body.paid_gross - totals["gross_pay"], 2)
    if abs(variance) >= 0.01:
        issues.append(
            f"Variance of ${abs(variance):.2f} detected — "
            f"calculated ${totals['gross_pay']:.2f}, paid ${body.paid_gross:.2f}"
        )
    if body.paid_notes:
        issues.append(body.paid_notes)

    return {
        "payslip_id":   body.payslip_id,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "employee":     body.employee.model_dump(),
        "award":        {"code": body.award_code, "name": award_name},
        "pay_period":   body.pay_period.model_dump(),
        "base_hourly_rate": rate,
        "shifts":       shift_calcs,
        "calculated":   totals,
        "paid": {
            "gross_pay": body.paid_gross,
            "notes":     body.paid_notes,
        },
        "audit": _audit(totals["gross_pay"], body.paid_gross, issues),
    }


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
