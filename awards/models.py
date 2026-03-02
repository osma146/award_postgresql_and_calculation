"""
Australian Modern Awards - Data Models
Covers the 4 salary factors: Classification, Wage, Penalty, Allowance/Expense
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DayType(Enum):
    WEEKDAY    = "weekday"
    SATURDAY   = "saturday"
    SUNDAY     = "sunday"
    PUBLIC_HOL = "public_holiday"


class ShiftType(Enum):
    ORDINARY  = "ordinary"     # standard daytime hours
    AFTERNOON = "afternoon"    # e.g. 12:00 – 18:00
    NIGHT     = "night"        # e.g. 18:00 – 06:00
    OVERTIME  = "overtime"


class AllowanceType(Enum):
    TRAVEL      = "travel"        # per km or flat rate
    MEAL        = "meal"          # overtime / away-from-base meal
    TOOL        = "tool"          # personal tools required for work
    UNIFORM     = "uniform"       # clothing / laundry
    FIRST_AID   = "first_aid"     # qualified first-aider on duty
    LEADING_HAND = "leading_hand" # supervisory responsibility
    OTHER       = "other"


# ---------------------------------------------------------------------------
# Factor 1 – Classification (Class)
# ---------------------------------------------------------------------------

@dataclass
class Classification:
    """
    A classification level within an Award.
    e.g. Retail Employee Level 1, Level 2 … Level 8
    """
    level: int              # numeric level (1, 2, 3 …)
    title: str              # human-readable name
    description: str = ""   # duties / competencies


# ---------------------------------------------------------------------------
# Factor 2 – Wage (base pay rate)
# ---------------------------------------------------------------------------

@dataclass
class WageRate:
    """
    The minimum base rate for a given classification.
    Rates are set / updated annually by the Fair Work Commission.
    """
    classification: Classification
    hourly_rate: float      # AUD per hour
    weekly_rate: float      # AUD per 38-hour week (for salaried employees)
    effective_date: str     # ISO date string e.g. "2024-07-01"


# ---------------------------------------------------------------------------
# Factor 3 – Penalty Rates
# ---------------------------------------------------------------------------

@dataclass
class PenaltyRule:
    """
    A single penalty loading rule that applies under specific conditions.
    The multiplier is applied to the base hourly rate.

    Examples:
        Saturday ordinary time  → multiplier = 1.25
        Sunday ordinary time    → multiplier = 2.00
        Public holiday          → multiplier = 2.25
        Overtime (first 2 hrs)  → multiplier = 1.50
        Overtime (after 2 hrs)  → multiplier = 2.00
        Night shift loading     → multiplier = 1.15  (shift allowance, often additive)
    """
    name: str
    day_type: Optional[DayType]
    shift_type: Optional[ShiftType]
    multiplier: float           # e.g. 1.5 = time-and-a-half
    overtime_after_hours: Optional[float] = None  # e.g. 2.0 → applies after 2 hrs OT


# ---------------------------------------------------------------------------
# Factor 4 – Allowances / Expenses
# ---------------------------------------------------------------------------

@dataclass
class Allowance:
    """
    An allowance or expense reimbursement payable in addition to base wage.
    Can be a flat rate per shift/day, per km, or per week.
    """
    name: str
    allowance_type: AllowanceType
    amount: float               # AUD
    unit: str                   # "per_shift" | "per_day" | "per_km" | "per_week"
    taxable: bool = True        # some reimbursements are non-taxable


# ---------------------------------------------------------------------------
# Award (combines all 4 factors)
# ---------------------------------------------------------------------------

@dataclass
class Award:
    """
    A Modern Award document.
    Contains classifications, wage rates, penalty rules, and allowances.
    """
    code: str                               # FWC Award code, e.g. "MA000004"
    name: str                               # e.g. "General Retail Industry Award 2020"
    classifications: list[Classification]  = field(default_factory=list)
    wage_rates: list[WageRate]             = field(default_factory=list)
    penalty_rules: list[PenaltyRule]       = field(default_factory=list)
    allowances: list[Allowance]            = field(default_factory=list)

    # Standard hours per week before overtime kicks in (usually 38)
    ordinary_hours_per_week: float = 38.0

    def get_wage_for_classification(self, level: int) -> Optional[WageRate]:
        for wr in self.wage_rates:
            if wr.classification.level == level:
                return wr
        return None

    def get_penalty_rule(
        self,
        day_type: DayType,
        shift_type: ShiftType,
        overtime_hours_worked: float = 0.0
    ) -> Optional[PenaltyRule]:
        """
        Return the most applicable penalty rule for the given conditions.
        Overtime rules take precedence when overtime hours are provided.
        """
        candidates = [
            r for r in self.penalty_rules
            if (r.day_type is None or r.day_type == day_type)
            and (r.shift_type is None or r.shift_type == shift_type)
        ]

        if overtime_hours_worked > 0:
            # prefer rules that specify an overtime threshold
            ot_rules = [
                r for r in candidates
                if r.overtime_after_hours is not None
                and overtime_hours_worked > r.overtime_after_hours
            ]
            if ot_rules:
                return max(ot_rules, key=lambda r: r.multiplier)

        return candidates[0] if candidates else None
