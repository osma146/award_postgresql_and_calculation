"""
Payslip Generator

Generates example payslip JSON files using real Award rates from the database.
Each payslip includes calculated (correct) pay, what was actually paid,
and an audit section flagging overpayment, underpayment, or correct payment.

Usage:
    python payslips/generator.py
"""

import os
import sys
import json
from datetime import date, datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
from dotenv import load_dotenv

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / ".env"))
OUT_DIR = Path(__file__).parent

AWARD_CODE = "MA000004"
AWARD_NAME = "General Retail Industry Award 2020"

# Penalty multipliers used in this award
PENALTY = {
    "weekday_ordinary": 1.00,
    "saturday":         1.50,
    "sunday":           2.00,
    "public_holiday":   2.25,
    "overtime_t1":      1.50,   # first 2 hrs overtime
    "overtime_t2":      2.00,   # after 2 hrs overtime
}

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "awards_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )


def get_rate(cur, level: int, lookup_date: date) -> float | None:
    cur.execute("""
        SELECT calculated_rate FROM classifications
        WHERE award_code = %s
          AND classification ILIKE %s
          AND operative_from <= %s
          AND (operative_to >= %s OR operative_to IS NULL)
          AND calculated_rate IS NOT NULL
        LIMIT 1
    """, (AWARD_CODE, f"%retail employee level {level}%", lookup_date, lookup_date))
    row = cur.fetchone()
    return float(row[0]) if row else None

# ---------------------------------------------------------------------------
# Calculation helpers
# ---------------------------------------------------------------------------

def calc_shift(base_rate: float, hours: float, day_type: str,
               overtime_hours: float = 0.0, allowances: list = None) -> dict:
    """Calculate correct pay for one shift."""
    ordinary_hours = max(hours - overtime_hours, 0.0)

    multiplier = PENALTY.get(day_type, 1.0)
    ordinary_pay = round(ordinary_hours * base_rate * multiplier, 2)

    # Overtime: first 2hrs at 1.5x, remainder at 2x
    ot_t1 = min(overtime_hours, 2.0)
    ot_t2 = max(overtime_hours - 2.0, 0.0)
    overtime_pay = round(
        ot_t1 * base_rate * PENALTY["overtime_t1"] +
        ot_t2 * base_rate * PENALTY["overtime_t2"], 2
    )

    allowance_total = round(sum(a["amount"] for a in (allowances or [])), 2)

    return {
        "ordinary_hours":    ordinary_hours,
        "ordinary_rate":     round(base_rate * multiplier, 4),
        "ordinary_pay":      ordinary_pay,
        "overtime_hours":    overtime_hours,
        "overtime_pay":      overtime_pay,
        "allowances_total":  allowance_total,
        "shift_gross":       round(ordinary_pay + overtime_pay + allowance_total, 2),
    }


def sum_period(shifts_calc: list) -> dict:
    return {
        "total_ordinary_pay": round(sum(s["ordinary_pay"] for s in shifts_calc), 2),
        "total_overtime_pay": round(sum(s["overtime_pay"] for s in shifts_calc), 2),
        "total_allowances":   round(sum(s["allowances_total"] for s in shifts_calc), 2),
        "gross_pay":          round(sum(s["shift_gross"] for s in shifts_calc), 2),
    }


def audit(calculated_gross: float, paid_gross: float, issues: list) -> dict:
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


def build_payslip(pid, employee, pay_period, shifts_input, correct_rate,
                  paid_gross, paid_notes, issues):
    """Assemble a full payslip dict."""
    calcs = []
    for s in shifts_input:
        c = calc_shift(
            correct_rate,
            s["hours_worked"],
            s["day_type"],
            s.get("overtime_hours", 0.0),
            s.get("allowances", []),
        )
        c["date"]              = s["date"]
        c["day_type"]          = s["day_type"]
        c["penalty_applied"]   = f"{PENALTY.get(s['day_type'], 1.0)*100:.0f}%"
        c["allowances_detail"] = s.get("allowances", [])
        calcs.append(c)

    totals = sum_period(calcs)

    return {
        "payslip_id":   pid,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "employee":     employee,
        "award": {
            "code": AWARD_CODE,
            "name": AWARD_NAME,
        },
        "pay_period":   pay_period,
        "shifts":       calcs,
        "calculated":   totals,
        "paid": {
            "gross_pay": paid_gross,
            "notes":     paid_notes,
        },
        "audit": audit(totals["gross_pay"], paid_gross, issues),
    }


# ---------------------------------------------------------------------------
# Payslip definitions
# ---------------------------------------------------------------------------

def generate_all(cur):
    payslips = []

    # --------------------------------------------------------
    # EMPLOYEE 1 — Jane Smith, Level 2, full-time
    # Scenario: CORRECTLY PAID, two pay periods
    # --------------------------------------------------------
    emp1 = {"id": "EMP001", "name": "Jane Smith",   "employment_type": "full_time"}
    r2_2023 = get_rate(cur, 2, date(2023, 9, 4))   # $25.29

    jane_shifts_sep = [
        {"date": "2023-09-04", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-09-05", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-09-07", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-09-09", "day_type": "saturday",         "hours_worked": 6.0},
        {"date": "2023-09-11", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-09-12", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-09-14", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-09-16", "day_type": "saturday",         "hours_worked": 6.0},
    ]
    correct_gross = round(sum(
        calc_shift(r2_2023, s["hours_worked"], s["day_type"])["shift_gross"]
        for s in jane_shifts_sep
    ), 2)
    payslips.append(build_payslip(
        "PS-2023-001", emp1,
        {"start": "2023-09-04", "end": "2023-09-17", "type": "fortnightly"},
        jane_shifts_sep, r2_2023,
        paid_gross=correct_gross,
        paid_notes="Correct — Level 2 rate applied, Saturday penalty included",
        issues=[],
    ))

    jane_shifts_oct = [
        {"date": "2023-10-02", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-10-03", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-10-05", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-10-07", "day_type": "saturday",         "hours_worked": 8.0},
        {"date": "2023-10-09", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-10-10", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-10-12", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-10-14", "day_type": "saturday",         "hours_worked": 8.0},
    ]
    correct_gross_oct = round(sum(
        calc_shift(r2_2023, s["hours_worked"], s["day_type"])["shift_gross"]
        for s in jane_shifts_oct
    ), 2)
    payslips.append(build_payslip(
        "PS-2023-002", emp1,
        {"start": "2023-10-02", "end": "2023-10-15", "type": "fortnightly"},
        jane_shifts_oct, r2_2023,
        paid_gross=correct_gross_oct,
        paid_notes="Correct — Level 2 rate applied, Saturday penalty included",
        issues=[],
    ))

    # --------------------------------------------------------
    # EMPLOYEE 2 — Mark Johnson, Level 3, full-time
    # Scenario: UNDERPAID — paid at Level 2 rate (wrong classification)
    # --------------------------------------------------------
    emp2 = {"id": "EMP002", "name": "Mark Johnson", "employment_type": "full_time"}
    r3_2023 = get_rate(cur, 3, date(2023, 11, 6))   # $25.68 correct
    r2_2023b = get_rate(cur, 2, date(2023, 11, 6))  # $25.29 — what was paid

    mark_shifts = [
        {"date": "2023-11-06", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-07", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-08", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-09", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-10", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-13", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-14", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-15", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-16", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2023-11-17", "day_type": "weekday_ordinary", "hours_worked": 8.0},
    ]
    wrong_gross = round(sum(
        calc_shift(r2_2023b, s["hours_worked"], s["day_type"])["shift_gross"]
        for s in mark_shifts
    ), 2)
    payslips.append(build_payslip(
        "PS-2023-003", emp2,
        {"start": "2023-11-06", "end": "2023-11-17", "type": "fortnightly"},
        mark_shifts, r3_2023,
        paid_gross=wrong_gross,
        paid_notes=f"ERROR — paid at Level 2 rate (${r2_2023b}/hr) instead of Level 3 (${r3_2023}/hr)",
        issues=[
            f"Wrong classification rate applied: paid ${r2_2023b}/hr, correct rate is ${r3_2023}/hr",
            "Employee is classified as Level 3 but system recorded as Level 2",
        ],
    ))

    # --------------------------------------------------------
    # EMPLOYEE 3 — Sarah Chen, Level 1, part-time
    # Scenario: OVERPAID — paid at Level 2 rate (classification entered incorrectly)
    # --------------------------------------------------------
    emp3 = {"id": "EMP003", "name": "Sarah Chen",   "employment_type": "part_time"}
    r1_2024 = get_rate(cur, 1, date(2024, 2, 5))    # $25.65 correct
    r2_2024 = get_rate(cur, 2, date(2024, 2, 5))    # $26.24 — what was paid

    sarah_shifts = [
        {"date": "2024-02-05", "day_type": "weekday_ordinary", "hours_worked": 6.0},
        {"date": "2024-02-07", "day_type": "weekday_ordinary", "hours_worked": 6.0},
        {"date": "2024-02-10", "day_type": "saturday",         "hours_worked": 5.0},
        {"date": "2024-02-12", "day_type": "weekday_ordinary", "hours_worked": 6.0},
        {"date": "2024-02-14", "day_type": "weekday_ordinary", "hours_worked": 6.0},
        {"date": "2024-02-17", "day_type": "saturday",         "hours_worked": 5.0},
    ]
    overpaid_gross = round(sum(
        calc_shift(r2_2024, s["hours_worked"], s["day_type"])["shift_gross"]
        for s in sarah_shifts
    ), 2)
    payslips.append(build_payslip(
        "PS-2024-001", emp3,
        {"start": "2024-02-05", "end": "2024-02-18", "type": "fortnightly"},
        sarah_shifts, r1_2024,
        paid_gross=overpaid_gross,
        paid_notes=f"ERROR — paid at Level 2 rate (${r2_2024}/hr) instead of Level 1 (${r1_2024}/hr)",
        issues=[
            f"Wrong classification rate applied: paid ${r2_2024}/hr, correct rate is ${r1_2024}/hr",
            "Employee is Level 1 but payroll system had Level 2 on file",
        ],
    ))

    # --------------------------------------------------------
    # EMPLOYEE 4 — Tom Baker, Level 2, full-time
    # Scenario: UNDERPAID — Sunday penalty not applied (paid base rate)
    # --------------------------------------------------------
    emp4 = {"id": "EMP004", "name": "Tom Baker",    "employment_type": "full_time"}
    r2_2024b = get_rate(cur, 2, date(2024, 3, 4))   # $26.24

    tom_shifts = [
        {"date": "2024-03-04", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-05", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-06", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-07", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-08", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-09", "day_type": "saturday",         "hours_worked": 8.0},
        {"date": "2024-03-10", "day_type": "sunday",           "hours_worked": 8.0},
        {"date": "2024-03-11", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-12", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-03-13", "day_type": "weekday_ordinary", "hours_worked": 8.0},
    ]
    # What was paid: Sunday treated as ordinary weekday (no penalty)
    wrong_tom = round(sum(
        calc_shift(r2_2024b, s["hours_worked"],
                   "weekday_ordinary" if s["day_type"] == "sunday" else s["day_type"])["shift_gross"]
        for s in tom_shifts
    ), 2)
    payslips.append(build_payslip(
        "PS-2024-002", emp4,
        {"start": "2024-03-04", "end": "2024-03-17", "type": "fortnightly"},
        tom_shifts, r2_2024b,
        paid_gross=wrong_tom,
        paid_notes="ERROR — Sunday worked 2024-03-10 paid at ordinary weekday rate (no 200% penalty applied)",
        issues=[
            "Sunday penalty not applied on 2024-03-10 (8.0 hrs)",
            f"Paid ${r2_2024b}/hr instead of ${round(r2_2024b * 2.0, 4)}/hr for Sunday",
            f"Underpayment on Sunday shift: ${round(8.0 * r2_2024b * (2.0 - 1.0), 2)}",
        ],
    ))

    # --------------------------------------------------------
    # EMPLOYEE 5 — Priya Patel, Level 4, casual
    # Scenario: UNDERPAID — overtime not paid correctly + missing allowance
    # --------------------------------------------------------
    emp5 = {"id": "EMP005", "name": "Priya Patel",  "employment_type": "casual"}
    r4_2024 = get_rate(cur, 4, date(2024, 4, 1))    # $27.17
    meal_allow = {"name": "Overtime meal allowance", "amount": 19.56, "unit": "per_occasion"}

    priya_shifts = [
        {"date": "2024-04-01", "day_type": "weekday_ordinary", "hours_worked": 8.0,
         "overtime_hours": 0.0, "allowances": []},
        {"date": "2024-04-02", "day_type": "weekday_ordinary", "hours_worked": 11.0,
         "overtime_hours": 3.0, "allowances": [meal_allow]},   # OT + meal
        {"date": "2024-04-03", "day_type": "weekday_ordinary", "hours_worked": 9.5,
         "overtime_hours": 1.5, "allowances": []},
        {"date": "2024-04-06", "day_type": "saturday",         "hours_worked": 8.0,
         "overtime_hours": 0.0, "allowances": []},
        {"date": "2024-04-07", "day_type": "sunday",           "hours_worked": 6.0,
         "overtime_hours": 0.0, "allowances": []},
        {"date": "2024-04-08", "day_type": "weekday_ordinary", "hours_worked": 10.0,
         "overtime_hours": 2.0, "allowances": [meal_allow]},   # OT + meal
    ]
    # What was paid: overtime paid at base rate only (no 1.5x), meal allowance missing
    wrong_priya = 0.0
    for s in priya_shifts:
        ord_hrs = max(s["hours_worked"] - s.get("overtime_hours", 0.0), 0.0)
        mult    = PENALTY.get(s["day_type"], 1.0)
        wrong_priya += ord_hrs * r4_2024 * mult
        wrong_priya += s.get("overtime_hours", 0.0) * r4_2024  # BUG: paid at 1x, not 1.5x/2x
        # meal allowance intentionally omitted
    wrong_priya = round(wrong_priya, 2)

    payslips.append(build_payslip(
        "PS-2024-003", emp5,
        {"start": "2024-04-01", "end": "2024-04-14", "type": "fortnightly"},
        priya_shifts, r4_2024,
        paid_gross=wrong_priya,
        paid_notes="ERROR — overtime paid at base rate (1x) instead of penalty rates; meal allowances not paid",
        issues=[
            "Overtime on 2024-04-02 (3.0 hrs): paid at 1.0x, should be 1.5x/2.0x",
            "Overtime on 2024-04-03 (1.5 hrs): paid at 1.0x, should be 1.5x",
            "Overtime on 2024-04-08 (2.0 hrs): paid at 1.0x, should be 1.5x",
            f"Meal allowances missing: 2 x ${meal_allow['amount']} = ${2 * meal_allow['amount']}",
        ],
    ))

    # --------------------------------------------------------
    # EMPLOYEE 6 — James Liu, Level 3, full-time
    # Scenario: UNDERPAID — public holiday worked, paid at ordinary rate
    # --------------------------------------------------------
    emp6 = {"id": "EMP006", "name": "James Liu",    "employment_type": "full_time"}
    r3_2024 = get_rate(cur, 3, date(2024, 6, 10))   # $26.65

    james_shifts = [
        {"date": "2024-06-10", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-11", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-12", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-13", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-14", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-17", "day_type": "public_holiday",   "hours_worked": 8.0},  # Queen's Birthday
        {"date": "2024-06-18", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-19", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-20", "day_type": "weekday_ordinary", "hours_worked": 8.0},
        {"date": "2024-06-21", "day_type": "weekday_ordinary", "hours_worked": 8.0},
    ]
    # What was paid: public holiday treated as ordinary weekday
    wrong_james = round(sum(
        calc_shift(r3_2024, s["hours_worked"], "weekday_ordinary")["shift_gross"]
        for s in james_shifts
    ), 2)
    correct_james = round(sum(
        calc_shift(r3_2024, s["hours_worked"], s["day_type"])["shift_gross"]
        for s in james_shifts
    ), 2)
    payslips.append(build_payslip(
        "PS-2024-004", emp6,
        {"start": "2024-06-10", "end": "2024-06-23", "type": "fortnightly"},
        james_shifts, r3_2024,
        paid_gross=wrong_james,
        paid_notes="ERROR — public holiday 2024-06-17 (Queen's Birthday) paid at ordinary weekday rate",
        issues=[
            "Public holiday penalty not applied on 2024-06-17 (8.0 hrs)",
            f"Paid ${r3_2024}/hr instead of ${round(r3_2024 * 2.25, 4)}/hr for public holiday",
            f"Underpayment on public holiday: ${round(8.0 * r3_2024 * (2.25 - 1.0), 2)}",
        ],
    ))

    return payslips


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n  Generating payslips from live Award data...\n")
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            payslips = generate_all(cur)
    finally:
        conn.close()

    counts = {"correct": 0, "underpaid": 0, "overpaid": 0}
    for ps in payslips:
        status = ps["audit"]["status"]
        counts[status] += 1
        path = OUT_DIR / f"{ps['payslip_id']}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ps, f, indent=2, ensure_ascii=False)
        variance = ps["audit"]["variance"]
        sign = "+" if variance > 0 else ""
        print(f"  [{status.upper():10s}]  {ps['payslip_id']}  "
              f"{ps['employee']['name']:15s}  variance: {sign}${variance:.2f}")

    print(f"\n  Generated {len(payslips)} payslips → payslips/")
    print(f"  Correct: {counts['correct']}  |  Underpaid: {counts['underpaid']}  |  Overpaid: {counts['overpaid']}\n")
