"""
Australian Modern Awards - Pay Calculation Engine

Computes an employee's gross pay for a shift or pay period using:
  Factor 1 - Classification (class / level)
  Factor 2 - Wage         (base hourly rate)
  Factor 3 - Penalty      (multipliers for day type, shift, overtime)
  Factor 4 - Allowances   (expenses added on top of wage)
"""

from dataclasses import dataclass, field
from typing import Optional
from .models import Award, DayType, ShiftType, AllowanceType, Allowance


# ---------------------------------------------------------------------------
# Input: describes one shift worked by an employee
# ---------------------------------------------------------------------------

@dataclass
class ShiftInput:
    """
    All the information needed to calculate pay for a single shift.
    """
    classification_level: int       # Factor 1 – employee's Award level
    hours_worked: float             # total hours on the shift
    day_type: DayType               # weekday / saturday / sunday / public_holiday
    shift_type: ShiftType           # ordinary / afternoon / night / overtime
    overtime_hours: float = 0.0    # hours worked beyond ordinary daily limit

    # Allowances that apply to this shift (caller selects relevant ones)
    applicable_allowances: list[Allowance] = field(default_factory=list)

    # For travel/km-based allowances
    kilometres_travelled: float = 0.0


# ---------------------------------------------------------------------------
# Output: detailed breakdown of calculated pay
# ---------------------------------------------------------------------------

@dataclass
class PayBreakdown:
    """
    Full breakdown of calculated gross pay for a shift.
    """
    classification_level: int
    base_hourly_rate: float

    # Ordinary hours (non-overtime)
    ordinary_hours: float
    ordinary_rate: float            # base rate × penalty multiplier
    ordinary_pay: float             # ordinary_hours × ordinary_rate

    # Overtime
    overtime_hours: float
    overtime_rate: float            # base rate × overtime multiplier
    overtime_pay: float

    # Penalty loading applied
    penalty_multiplier: float
    penalty_description: str

    # Allowances
    allowances_breakdown: list[dict]   # [{name, amount, unit, subtotal}]
    total_allowances: float

    # Grand total
    gross_pay: float

    def summary(self) -> str:
        lines = [
            f"=== Pay Breakdown ===",
            f"Classification Level : {self.classification_level}",
            f"Base Hourly Rate     : ${self.base_hourly_rate:.4f}",
            f"",
            f"--- Ordinary Time ---",
            f"Hours               : {self.ordinary_hours:.2f}",
            f"Rate (×{self.penalty_multiplier:.2f})         : ${self.ordinary_rate:.4f}/hr",
            f"Pay                 : ${self.ordinary_pay:.2f}",
            f"Penalty Applied     : {self.penalty_description}",
            f"",
            f"--- Overtime ---",
            f"Hours               : {self.overtime_hours:.2f}",
            f"Rate                : ${self.overtime_rate:.4f}/hr",
            f"Pay                 : ${self.overtime_pay:.2f}",
            f"",
            f"--- Allowances & Expenses ---",
        ]
        for a in self.allowances_breakdown:
            lines.append(f"  {a['name']:25s}: ${a['subtotal']:.2f} ({a['unit']})")
        lines += [
            f"Total Allowances    : ${self.total_allowances:.2f}",
            f"",
            f"{'='*30}",
            f"GROSS PAY           : ${self.gross_pay:.2f}",
            f"{'='*30}",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Calculator
# ---------------------------------------------------------------------------

class AwardsCalculator:
    """
    Calculates gross pay for a shift under a specific Modern Award.

    Usage:
        calc = AwardsCalculator(award)
        result = calc.calculate(shift_input)
        print(result.summary())
    """

    def __init__(self, award: Award):
        self.award = award

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(self, shift: ShiftInput) -> PayBreakdown:
        """Calculate gross pay for a single shift."""

        # --- Factor 1 + 2: Classification & Wage ---
        wage_rate = self.award.get_wage_for_classification(shift.classification_level)
        if wage_rate is None:
            raise ValueError(
                f"No wage rate found for classification level {shift.classification_level} "
                f"in Award '{self.award.name}'"
            )
        base_rate = wage_rate.hourly_rate

        # --- Factor 3: Penalty Rate ---
        ordinary_hours = max(shift.hours_worked - shift.overtime_hours, 0.0)

        penalty_rule = self.award.get_penalty_rule(
            day_type=shift.day_type,
            shift_type=shift.shift_type,
            overtime_hours_worked=0.0,          # ordinary time penalty
        )
        penalty_multiplier = penalty_rule.multiplier if penalty_rule else 1.0
        penalty_description = penalty_rule.name if penalty_rule else "No penalty (base rate)"

        ordinary_rate = base_rate * penalty_multiplier
        ordinary_pay  = ordinary_hours * ordinary_rate

        # Overtime penalty (separate rule lookup)
        overtime_rule = self.award.get_penalty_rule(
            day_type=shift.day_type,
            shift_type=ShiftType.OVERTIME,
            overtime_hours_worked=shift.overtime_hours,
        )
        overtime_multiplier = overtime_rule.multiplier if overtime_rule else 1.5
        overtime_rate = base_rate * overtime_multiplier
        overtime_pay  = shift.overtime_hours * overtime_rate

        # --- Factor 4: Allowances / Expenses ---
        allowances_breakdown, total_allowances = self._calculate_allowances(
            shift.applicable_allowances,
            shift.kilometres_travelled,
        )

        gross_pay = ordinary_pay + overtime_pay + total_allowances

        return PayBreakdown(
            classification_level = shift.classification_level,
            base_hourly_rate     = base_rate,
            ordinary_hours       = ordinary_hours,
            ordinary_rate        = ordinary_rate,
            ordinary_pay         = ordinary_pay,
            overtime_hours       = shift.overtime_hours,
            overtime_rate        = overtime_rate,
            overtime_pay         = overtime_pay,
            penalty_multiplier   = penalty_multiplier,
            penalty_description  = penalty_description,
            allowances_breakdown = allowances_breakdown,
            total_allowances     = total_allowances,
            gross_pay            = gross_pay,
        )

    def calculate_period(self, shifts: list[ShiftInput]) -> dict:
        """
        Calculate total pay across multiple shifts (e.g. a pay period / fortnight).
        Returns a summary dict with per-shift breakdowns and totals.
        """
        breakdowns = [self.calculate(s) for s in shifts]
        total_gross = sum(b.gross_pay for b in breakdowns)
        total_ordinary = sum(b.ordinary_pay for b in breakdowns)
        total_overtime = sum(b.overtime_pay for b in breakdowns)
        total_allowances = sum(b.total_allowances for b in breakdowns)

        return {
            "shifts": breakdowns,
            "total_ordinary_pay": round(total_ordinary, 2),
            "total_overtime_pay": round(total_overtime, 2),
            "total_allowances":   round(total_allowances, 2),
            "total_gross_pay":    round(total_gross, 2),
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calculate_allowances(
        self,
        allowances: list[Allowance],
        kilometres: float,
    ) -> tuple[list[dict], float]:
        breakdown = []
        total = 0.0

        for a in allowances:
            if a.unit == "per_km":
                subtotal = a.amount * kilometres
            elif a.unit in ("per_shift", "per_day", "flat"):
                subtotal = a.amount
            elif a.unit == "per_week":
                # caller decides how many shifts make up a week — pass weekly amount directly
                subtotal = a.amount
            else:
                subtotal = a.amount   # default: take amount as-is

            breakdown.append({
                "name":    a.name,
                "type":    a.allowance_type.value,
                "amount":  a.amount,
                "unit":    a.unit,
                "subtotal": round(subtotal, 4),
                "taxable": a.taxable,
            })
            total += subtotal

        return breakdown, round(total, 2)
