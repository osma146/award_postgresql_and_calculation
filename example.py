"""
Example: Retail Industry Award 2020 - Pay Calculation
Demonstrates all 4 factors: Classification, Wage, Penalty, Allowance
"""

from awards import (
    Award, Classification, WageRate, PenaltyRule, Allowance,
    DayType, ShiftType, AllowanceType,
    AwardsCalculator, ShiftInput,
)

# ===========================================================================
# 1. Define the Award
# ===========================================================================

retail_award = Award(
    code="MA000004",
    name="General Retail Industry Award 2020",
    ordinary_hours_per_week=38.0,
)

# ---------------------------------------------------------------------------
# Factor 1 – Classifications (Levels 1–3 for this example)
# ---------------------------------------------------------------------------
level1 = Classification(level=1, title="Retail Employee Level 1",
                        description="Entry level, basic duties")
level2 = Classification(level=2, title="Retail Employee Level 2",
                        description="Experienced, handles customer queries")
level3 = Classification(level=3, title="Retail Employee Level 3",
                        description="Senior, supervisory duties")

retail_award.classifications = [level1, level2, level3]

# ---------------------------------------------------------------------------
# Factor 2 – Wage Rates (FY 2024-25 approximate rates)
# ---------------------------------------------------------------------------
retail_award.wage_rates = [
    WageRate(classification=level1, hourly_rate=23.23, weekly_rate=882.74, effective_date="2024-07-01"),
    WageRate(classification=level2, hourly_rate=24.10, weekly_rate=915.80, effective_date="2024-07-01"),
    WageRate(classification=level3, hourly_rate=25.16, weekly_rate=956.08, effective_date="2024-07-01"),
]

# ---------------------------------------------------------------------------
# Factor 3 – Penalty Rules
# ---------------------------------------------------------------------------
retail_award.penalty_rules = [
    PenaltyRule(name="Weekday ordinary",      day_type=DayType.WEEKDAY,    shift_type=ShiftType.ORDINARY,  multiplier=1.00),
    PenaltyRule(name="Afternoon shift",       day_type=None,               shift_type=ShiftType.AFTERNOON, multiplier=1.15),
    PenaltyRule(name="Night shift",           day_type=None,               shift_type=ShiftType.NIGHT,     multiplier=1.30),
    PenaltyRule(name="Saturday",              day_type=DayType.SATURDAY,   shift_type=ShiftType.ORDINARY,  multiplier=1.25),
    PenaltyRule(name="Sunday",                day_type=DayType.SUNDAY,     shift_type=ShiftType.ORDINARY,  multiplier=2.00),
    PenaltyRule(name="Public holiday",        day_type=DayType.PUBLIC_HOL, shift_type=ShiftType.ORDINARY,  multiplier=2.25),
    PenaltyRule(name="Overtime (first 2 hrs)",day_type=DayType.WEEKDAY,    shift_type=ShiftType.OVERTIME,  multiplier=1.50, overtime_after_hours=0),
    PenaltyRule(name="Overtime (after 2 hrs)",day_type=DayType.WEEKDAY,    shift_type=ShiftType.OVERTIME,  multiplier=2.00, overtime_after_hours=2),
]

# ---------------------------------------------------------------------------
# Factor 4 – Allowances / Expenses
# ---------------------------------------------------------------------------
travel_allowance  = Allowance(name="Vehicle allowance",  allowance_type=AllowanceType.TRAVEL,      amount=0.99,   unit="per_km",    taxable=False)
meal_allowance    = Allowance(name="Overtime meal",      allowance_type=AllowanceType.MEAL,         amount=18.29,  unit="per_shift", taxable=True)
first_aid         = Allowance(name="First aid",          allowance_type=AllowanceType.FIRST_AID,    amount=14.40,  unit="per_shift", taxable=True)
leading_hand      = Allowance(name="Leading hand (3-10)",allowance_type=AllowanceType.LEADING_HAND, amount=42.21,  unit="per_week",  taxable=True)

# ===========================================================================
# 2. Create Calculator
# ===========================================================================

calc = AwardsCalculator(retail_award)

# ===========================================================================
# 3. Calculate individual shifts
# ===========================================================================

print("\n" + "="*60)
print("SCENARIO A: Level 2 employee, weekday ordinary shift (8 hrs)")
print("="*60)
shift_a = ShiftInput(
    classification_level=2,
    hours_worked=8.0,
    day_type=DayType.WEEKDAY,
    shift_type=ShiftType.ORDINARY,
    overtime_hours=0.0,
)
result_a = calc.calculate(shift_a)
print(result_a.summary())


print("\n" + "="*60)
print("SCENARIO B: Level 1 employee, Sunday shift (6 hrs) + travel")
print("="*60)
shift_b = ShiftInput(
    classification_level=1,
    hours_worked=6.0,
    day_type=DayType.SUNDAY,
    shift_type=ShiftType.ORDINARY,
    overtime_hours=0.0,
    applicable_allowances=[travel_allowance],
    kilometres_travelled=25.0,
)
result_b = calc.calculate(shift_b)
print(result_b.summary())


print("\n" + "="*60)
print("SCENARIO C: Level 3 leading hand, weekday with 3 hrs overtime")
print("  + meal allowance + first aid + leading hand allowance")
print("="*60)
shift_c = ShiftInput(
    classification_level=3,
    hours_worked=11.0,          # 8 ordinary + 3 overtime
    day_type=DayType.WEEKDAY,
    shift_type=ShiftType.OVERTIME,
    overtime_hours=3.0,
    applicable_allowances=[meal_allowance, first_aid, leading_hand],
)
result_c = calc.calculate(shift_c)
print(result_c.summary())


print("\n" + "="*60)
print("SCENARIO D: Pay period summary (Scenarios A + B + C)")
print("="*60)
period = calc.calculate_period([shift_a, shift_b, shift_c])
print(f"  Ordinary Pay  : ${period['total_ordinary_pay']:.2f}")
print(f"  Overtime Pay  : ${period['total_overtime_pay']:.2f}")
print(f"  Allowances    : ${period['total_allowances']:.2f}")
print(f"  TOTAL GROSS   : ${period['total_gross_pay']:.2f}")
