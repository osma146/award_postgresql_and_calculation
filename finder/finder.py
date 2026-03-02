"""
Award Data Finder

Reads finder/input.json, searches the database for the best matching
Award, Classification, Penalties, and Allowances, then writes the
resolved data to finder/output.json for use in downstream calculations.

Usage:
    python finder/finder.py
    python finder/finder.py --input finder/input.json
    python finder/finder.py --input finder/input.json --top 5
"""

import os
import sys
import json
import argparse
from datetime import date, datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(dotenv_path=str(Path(__file__).parent.parent / ".env"))

ROOT = Path(__file__).parent.parent
DEFAULT_INPUT  = ROOT / "finder" / "input.json"
DEFAULT_OUTPUT = ROOT / "finder" / "output.json"

# ---------------------------------------------------------------------------
# DB
# ---------------------------------------------------------------------------

def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "awards_db"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", ""),
    )

# ---------------------------------------------------------------------------
# Search helpers
# ---------------------------------------------------------------------------

def search_awards(cur, term: str, top: int = 5) -> list[dict]:
    """
    Search awards by name using both ILIKE and fuzzy (word_similarity).
    Returns top results ranked by best match score.
    """
    cur.execute("""
        SELECT DISTINCT ON (award_code)
            award_code,
            name,
            ROUND(
                GREATEST(
                    CASE WHEN name ILIKE %s THEN 1.0 ELSE 0.0 END,
                    MAX(word_similarity(%s, name)) OVER (PARTITION BY award_code)
                )::numeric, 2
            ) AS score
        FROM awards
        WHERE name ILIKE %s
           OR word_similarity(%s, name) > 0.3
        ORDER BY award_code, score DESC
        LIMIT %s
    """, (f"%{term}%", term, f"%{term}%", term, top))

    return [
        {"award_code": r[0], "name": r[1], "match_score": float(r[2])}
        for r in cur.fetchall()
    ]


def search_classifications(cur, award_code: str, term: str,
                           lookup_date: date | None, top: int = 5) -> list[dict]:
    """
    Search classifications for a given award by name/level keyword.
    Optionally filters by operative date for point-in-time accuracy.
    """
    date_filter = ""
    params_base = [award_code]

    if lookup_date:
        date_filter = "AND operative_from <= %s AND (operative_to >= %s OR operative_to IS NULL)"
        params_base += [lookup_date, lookup_date]

    cur.execute(f"""
        SELECT classification_fixed_id, classification, classification_level,
               base_rate, base_rate_type, calculated_rate, calculated_rate_type,
               operative_from, operative_to, score
        FROM (
            SELECT DISTINCT ON (classification_fixed_id)
                classification_fixed_id,
                classification,
                classification_level,
                base_rate,
                base_rate_type,
                calculated_rate,
                calculated_rate_type,
                operative_from,
                operative_to,
                ROUND(
                    GREATEST(
                        CASE WHEN classification ILIKE %s THEN 0.9 ELSE 0.0 END,
                        word_similarity(%s, COALESCE(classification, ''))
                    )::numeric, 2
                ) AS score
            FROM classifications
            WHERE award_code = %s
              {date_filter}
              AND (classification ILIKE %s OR word_similarity(%s, COALESCE(classification, '')) > 0.2)
              AND classification IS NOT NULL
            ORDER BY classification_fixed_id, score DESC
        ) ranked
        ORDER BY score DESC
        LIMIT %s
    """, [f"%{term}%", term] + params_base + [f"%{term}%", term, top])

    rows = cur.fetchall()
    return [
        {
            "classification_fixed_id": r[0],
            "classification":          r[1],
            "classification_level":    r[2],
            "base_rate_weekly":        float(r[3]) if r[3] is not None else None,
            "base_rate_type":          r[4],
            "calculated_rate_hourly":  float(r[5]) if r[5] is not None else None,
            "calculated_rate_type":    r[6],
            "operative_from":          r[7].isoformat() if r[7] else None,
            "operative_to":            r[8].isoformat() if r[8] else None,
            "match_score":             float(r[9]),
        }
        for r in rows
    ]


def get_penalties(cur, award_code: str, classification_name: str,
                  lookup_date: date | None) -> list[dict]:
    """
    Fetch penalty rates for the award.
    Tries to match by classification name first; falls back to all penalties
    for the award if no classification-specific rows are found.
    """
    date_filter = ""
    date_params = []
    if lookup_date:
        date_filter = "AND operative_from <= %s AND (operative_to >= %s OR operative_to IS NULL)"
        date_params = [lookup_date, lookup_date]

    # First try: penalties matching the specific classification name
    cur.execute(f"""
        SELECT penalty_fixed_id, penalty_description, employee_rate_type_code,
               rate, penalty_rate_unit, penalty_calculated_value,
               clause, operative_from, operative_to, classification
        FROM penalties
        WHERE award_code = %s
          AND classification ILIKE %s
          {date_filter}
          AND penalty_description IS NOT NULL
        ORDER BY classification, penalty_description
    """, [award_code, f"%{classification_name}%"] + date_params)

    rows = cur.fetchall()

    # Fallback: all penalties for the award if classification-specific search found nothing
    if not rows:
        cur.execute(f"""
            SELECT penalty_fixed_id, penalty_description, employee_rate_type_code,
                   rate, penalty_rate_unit, penalty_calculated_value,
                   clause, operative_from, operative_to, classification
            FROM penalties
            WHERE award_code = %s
              {date_filter}
              AND penalty_description IS NOT NULL
            ORDER BY classification, penalty_description
        """, [award_code] + date_params)
        rows = cur.fetchall()

    return [
        {
            "penalty_fixed_id":   r[0],
            "description":        r[1],
            "employee_rate_type": r[2],
            "rate":               float(r[3]) if r[3] is not None else None,
            "rate_unit":          r[4],
            "calculated_value":   float(r[5]) if r[5] is not None else None,
            "clause":             r[6],
            "operative_from":     r[7].isoformat() if r[7] else None,
            "operative_to":       r[8].isoformat() if r[8] else None,
            "classification":     r[9],
        }
        for r in rows
    ]


def get_expense_allowances(cur, award_code: str, lookup_date: date | None) -> list[dict]:
    """Fetch expense allowances for the resolved award."""
    date_filter = ""
    params = [award_code]

    if lookup_date:
        date_filter = "AND operative_from <= %s AND (operative_to >= %s OR operative_to IS NULL)"
        params += [lookup_date, lookup_date]

    cur.execute(f"""
        SELECT
            expense_allowance_fixed_id,
            allowance,
            parent_allowance,
            allowance_amount,
            payment_frequency,
            is_all_purpose,
            clause,
            operative_from,
            operative_to
        FROM expense_allowances
        WHERE award_code = %s
          {date_filter}
          AND allowance IS NOT NULL
        ORDER BY allowance
    """, params)

    return [
        {
            "expense_allowance_fixed_id": r[0],
            "allowance":                  r[1],
            "parent_allowance":           r[2],
            "amount":                     float(r[3]) if r[3] is not None else None,
            "payment_frequency":          r[4],
            "is_all_purpose":             r[5],
            "clause":                     r[6],
            "operative_from":             r[7].isoformat() if r[7] else None,
            "operative_to":               r[8].isoformat() if r[8] else None,
        }
        for r in cur.fetchall()
    ]


def get_wage_allowances(cur, award_code: str, lookup_date: date | None) -> list[dict]:
    """Fetch wage allowances for the resolved award."""
    date_filter = ""
    params = [award_code]

    if lookup_date:
        date_filter = "AND operative_from <= %s AND (operative_to >= %s OR operative_to IS NULL)"
        params += [lookup_date, lookup_date]

    cur.execute(f"""
        SELECT
            wage_allowance_fixed_id,
            allowance,
            parent_allowance,
            rate,
            base_rate,
            rate_unit,
            allowance_amount,
            payment_frequency,
            is_all_purpose,
            clause,
            operative_from,
            operative_to
        FROM wage_allowances
        WHERE award_code = %s
          {date_filter}
          AND allowance IS NOT NULL
        ORDER BY allowance
    """, params)

    return [
        {
            "wage_allowance_fixed_id": r[0],
            "allowance":               r[1],
            "parent_allowance":        r[2],
            "rate":                    float(r[3]) if r[3] is not None else None,
            "base_rate":               float(r[4]) if r[4] is not None else None,
            "rate_unit":               r[5],
            "allowance_amount":        float(r[6]) if r[6] is not None else None,
            "payment_frequency":       r[7],
            "is_all_purpose":          r[8],
            "clause":                  r[9],
            "operative_from":          r[10].isoformat() if r[10] else None,
            "operative_to":            r[11].isoformat() if r[11] else None,
        }
        for r in cur.fetchall()
    ]

# ---------------------------------------------------------------------------
# Main find logic
# ---------------------------------------------------------------------------

def find(input_path: Path, output_path: Path, top: int = 3):
    # Load input
    with open(input_path, encoding="utf-8") as f:
        query = json.load(f)

    award_term     = query.get("award", "")
    class_term     = query.get("classification", "")
    date_str       = query.get("date")
    want_penalties = query.get("include_penalties", True)
    want_allowances= query.get("include_allowances", True)

    lookup_date = None
    if date_str:
        lookup_date = datetime.strptime(date_str, "%Y-%m-%d").date()

    print(f"\n  Award search      : \"{award_term}\"")
    print(f"  Classification    : \"{class_term}\"")
    print(f"  Date              : {date_str or 'latest'}")

    conn = get_conn()
    try:
        with conn.cursor() as cur:

            # --- Step 1: Find award ---
            print(f"\n  Searching awards...")
            award_matches = search_awards(cur, award_term, top=top)

            if not award_matches:
                print("  No awards found for that search term.")
                return

            best_award = award_matches[0]
            print(f"  Top match  : {best_award['name']} ({best_award['award_code']})  score={best_award['match_score']}")
            if len(award_matches) > 1:
                for alt in award_matches[1:]:
                    print(f"  Alternative: {alt['name']} ({alt['award_code']})  score={alt['match_score']}")

            # --- Step 2: Find classification ---
            print(f"\n  Searching classifications...")
            class_matches = search_classifications(
                cur, best_award["award_code"], class_term, lookup_date, top=top
            )

            best_class = class_matches[0] if class_matches else None
            if best_class:
                print(f"  Top match  : {best_class['classification']}  "
                      f"hourly=${best_class['calculated_rate_hourly']}  score={best_class['match_score']}")
                for alt in class_matches[1:]:
                    print(f"  Alternative: {alt['classification']}  "
                          f"hourly=${alt['calculated_rate_hourly']}  score={alt['match_score']}")
            else:
                print("  No classifications found.")

            # --- Step 3: Penalties ---
            penalties = []
            if want_penalties and best_class:
                print(f"\n  Fetching penalties...")
                penalties = get_penalties(
                    cur,
                    best_award["award_code"],
                    best_class["classification"],
                    lookup_date,
                )
                print(f"  Found {len(penalties)} penalty rows")

            # --- Step 4: Allowances ---
            expense_allowances = []
            wage_allowances    = []
            if want_allowances:
                print(f"\n  Fetching allowances...")
                expense_allowances = get_expense_allowances(cur, best_award["award_code"], lookup_date)
                wage_allowances    = get_wage_allowances(cur, best_award["award_code"], lookup_date)
                print(f"  Found {len(expense_allowances)} expense allowances, "
                      f"{len(wage_allowances)} wage allowances")

    finally:
        conn.close()

    # --- Build output ---
    output = {
        "query": query,
        "resolved_at": datetime.now().isoformat(timespec="seconds"),
        "award": {
            "top_match": best_award,
            "alternatives": award_matches[1:],
        },
        "classification": {
            "top_match": best_class,
            "alternatives": class_matches[1:] if class_matches else [],
        },
        "penalties":          penalties,
        "expense_allowances": expense_allowances,
        "wage_allowances":    wage_allowances,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Output written to: {output_path.relative_to(ROOT)}")
    print(f"  Penalties        : {len(penalties)}")
    print(f"  Expense allow.   : {len(expense_allowances)}")
    print(f"  Wage allow.      : {len(wage_allowances)}")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find Award data by search terms")
    parser.add_argument("--input",  default=str(DEFAULT_INPUT),  help="Path to input JSON file")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output JSON file")
    parser.add_argument("--top",    default=3, type=int,         help="Number of alternative matches to show (default 3)")
    args = parser.parse_args()

    print("\n" + "="*50)
    print("  Award Data Finder")
    print("="*50)

    find(
        input_path=Path(args.input),
        output_path=Path(args.output),
        top=args.top,
    )

    print("="*50 + "\n")
