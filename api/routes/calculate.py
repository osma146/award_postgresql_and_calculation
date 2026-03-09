"""
Pay calculator endpoints

POST /calculate/shift    Calculate gross pay for a single shift
POST /calculate/period   Calculate total pay across multiple shifts (pay period)

Looks up the real Award rate from the DB then applies all 4 salary factors:
  1. Classification — hourly rate for the given level on the given date
  2. Wage           — base rate × penalty multiplier
  3. Penalty        — weekend / public holiday / overtime multipliers
  4. Allowances     — flat / per-km / per-shift amounts added on top
"""

from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

from api.auth import verify_api_key
from api.db import get_cursor
from api.limiter import limiter

router = APIRouter(
    prefix="/calculate",
    tags=["Calculator"],
    dependencies=[Depends(verify_api_key)],
)

# ---------------------------------------------------------------------------
# Penalty multipliers (standard Modern Award values)
# ---------------------------------------------------------------------------

PENALTY = {
    "weekday_ordinary": 1.00,
    "saturday":         1.50,
    "sunday":           2.00,
    "public_holiday":   2.25,
    "overtime_t1":      1.50,   # first 2 hrs overtime
    "overtime_t2":      2.00,   # after 2 hrs overtime
}

VALID_DAY_TYPES = set(PENALTY.keys())

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class AllowanceInput(BaseModel):
    name: str
    amount: float = Field(..., ge=0)
    unit: Literal["per_shift", "per_day", "per_km", "per_week", "flat"] = "per_shift"
    kilometres: float = Field(0.0, ge=0)  # only used when unit = per_km


class ShiftInput(BaseModel):
    date: Date
    day_type: str = Field(..., description="weekday_ordinary | saturday | sunday | public_holiday")
    hours_worked: float = Field(..., gt=0, le=24)
    overtime_hours: float = Field(0.0, ge=0)
    allowances: list[AllowanceInput] = []


class CalculateShiftRequest(BaseModel):
    award_code: str = Field(..., min_length=3, max_length=20)
    classification_level: int = Field(..., ge=1, le=20)
    shift: ShiftInput


class CalculatePeriodRequest(BaseModel):
    award_code: str = Field(..., min_length=3, max_length=20)
    classification_level: int = Field(..., ge=1, le=20)
    shifts: list[ShiftInput] = Field(..., min_length=1, max_length=100)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _lookup_rate(cur, award_code: str, level: int, lookup_date: Date) -> float:
    """Fetch the hourly rate for a classification level on a specific date."""
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
            detail=(
                f"No rate found for award '{award_code}', "
                f"level {level}, date {lookup_date}. "
                "Check that the award code, level, and date are valid."
            ),
        )
    return float(row[0])


def _calc_shift(base_rate: float, shift: ShiftInput) -> dict:
    """Core calculation — applies all 4 salary factors for one shift."""
    day = shift.day_type
    if day not in VALID_DAY_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid day_type '{day}'. Must be one of: {sorted(VALID_DAY_TYPES)}",
        )

    ordinary_hours = max(shift.hours_worked - shift.overtime_hours, 0.0)
    multiplier     = PENALTY[day]
    ordinary_rate  = round(base_rate * multiplier, 4)
    ordinary_pay   = round(ordinary_hours * ordinary_rate, 2)

    # Overtime: first 2 hrs at 1.5×, remainder at 2×
    ot_t1      = min(shift.overtime_hours, 2.0)
    ot_t2      = max(shift.overtime_hours - 2.0, 0.0)
    ot_rate_t1 = round(base_rate * PENALTY["overtime_t1"], 4)
    ot_rate_t2 = round(base_rate * PENALTY["overtime_t2"], 4)
    overtime_pay = round(ot_t1 * ot_rate_t1 + ot_t2 * ot_rate_t2, 2)

    # Allowances
    allowance_lines = []
    for a in shift.allowances:
        if a.unit == "per_km":
            subtotal = round(a.amount * a.kilometres, 2)
        else:
            subtotal = round(a.amount, 2)
        allowance_lines.append({"name": a.name, "unit": a.unit, "amount": a.amount, "subtotal": subtotal})
    allowance_total = round(sum(x["subtotal"] for x in allowance_lines), 2)

    return {
        "date":             str(shift.date),
        "day_type":         day,
        "penalty_applied":  f"{multiplier * 100:.0f}%",
        "base_hourly_rate": base_rate,
        "ordinary_hours":   ordinary_hours,
        "ordinary_rate":    ordinary_rate,
        "ordinary_pay":     ordinary_pay,
        "overtime_hours":   shift.overtime_hours,
        "overtime_pay":     overtime_pay,
        "allowances":       allowance_lines,
        "allowances_total": allowance_total,
        "shift_gross":      round(ordinary_pay + overtime_pay + allowance_total, 2),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/shift", summary="Calculate gross pay for a single shift")
@limiter.limit("60/minute")
def calculate_shift(request: Request, body: CalculateShiftRequest):
    """
    Calculate gross pay for a single shift using real Award rates from the database.

    Applies all 4 salary factors:
    - **Classification** — looks up the hourly rate for the level on the shift date
    - **Wage** — base rate × penalty multiplier
    - **Penalty** — weekend / public holiday / overtime multipliers
    - **Allowances** — flat / per-km / per-shift amounts

    **Day types:** `weekday_ordinary`, `saturday`, `sunday`, `public_holiday`
    """
    with get_cursor() as cur:
        rate = _lookup_rate(cur, body.award_code, body.classification_level, body.shift.date)
    result = _calc_shift(rate, body.shift)
    result["award_code"]            = body.award_code
    result["classification_level"]  = body.classification_level
    return result


@router.post("/period", summary="Calculate total pay across a pay period (multiple shifts)")
@limiter.limit("30/minute")
def calculate_period(request: Request, body: CalculatePeriodRequest):
    """
    Calculate gross pay across multiple shifts — a full pay period or fortnight.

    Uses the date of the **first shift** to look up the applicable Award rate.
    Returns per-shift breakdowns plus totals.
    """
    lookup_date = body.shifts[0].date
    with get_cursor() as cur:
        rate = _lookup_rate(cur, body.award_code, body.classification_level, lookup_date)

    breakdowns = [_calc_shift(rate, s) for s in body.shifts]

    return {
        "award_code":           body.award_code,
        "classification_level": body.classification_level,
        "base_hourly_rate":     rate,
        "rate_lookup_date":     str(lookup_date),
        "shifts":               breakdowns,
        "totals": {
            "total_ordinary_pay": round(sum(s["ordinary_pay"]     for s in breakdowns), 2),
            "total_overtime_pay": round(sum(s["overtime_pay"]     for s in breakdowns), 2),
            "total_allowances":   round(sum(s["allowances_total"] for s in breakdowns), 2),
            "gross_pay":          round(sum(s["shift_gross"]      for s in breakdowns), 2),
        },
    }
