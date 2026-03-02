"""
New Year Data Update Tool

Run this script when a new year's Excel files are available.
It guides you through the process step by step and checks for
problems before writing anything to the database.

Usage:
    python etl/add_new_year.py
    python etl/add_new_year.py --year 2026
"""

import argparse
import os
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import pandas as pd
from dotenv import load_dotenv

load_dotenv()

EXCEL_BASE = Path(__file__).parent.parent / "exel"

REQUIRED_FILE_PATTERNS = [
    "award",
    "classification",
    "expense-allowance",
    "penalty",
    "wage-allowance",
]

# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------

def check_folder(year: int) -> tuple[bool, list[str]]:
    """Check the year folder exists and contains the expected files."""
    folder = EXCEL_BASE / str(year)
    issues = []

    if not folder.exists():
        issues.append(f"Folder not found: {folder}")
        return False, issues

    files = list(folder.glob("*.xlsx"))
    if not files:
        issues.append(f"No .xlsx files found in {folder}")
        return False, issues

    found_types = []
    for f in files:
        name = f.stem.lower().replace("map-", "").replace(f"-export-{year}", "").replace(f"_export_{year}", "")
        for pattern in REQUIRED_FILE_PATTERNS:
            if pattern.replace("-", "") in name.replace("-", ""):
                found_types.append(pattern)
                break

    for pattern in REQUIRED_FILE_PATTERNS:
        if pattern not in found_types:
            issues.append(f"Missing file for type: {pattern}")

    return len(issues) == 0, issues


def check_columns(year: int) -> tuple[bool, list[str]]:
    """Open each Excel file and confirm key columns are present."""
    folder = EXCEL_BASE / str(year)
    issues = []

    REQUIRED_COLS = {
        "award":             ["awardcode", "awardfixedid", "name"],
        "classification":    ["awardcode", "classificationfixedid", "classificationlevel", "calculatedrate"],
        "penalty":           ["awardcode", "penaltyfixedid", "rate", "penaltycalculatedvalue"],
        "expense-allowance": ["awardcode", "expenseallowancefixedid", "allowanceamount"],
        "wage-allowance":    ["awardcode", "wageallowancefixedid", "allowanceamount"],
    }

    for f in sorted(folder.glob("*.xlsx")):
        ftype = None
        name = f.stem.lower().replace("map-", "").replace(f"-export-{year}", "")
        for pattern in REQUIRED_FILE_PATTERNS:
            if pattern.replace("-", "") in name.replace("-", ""):
                ftype = pattern
                break

        if ftype is None or ftype not in REQUIRED_COLS:
            continue

        try:
            df = pd.read_excel(f, nrows=1)
            actual_cols = [c.strip().lower() for c in df.columns]
            for req in REQUIRED_COLS[ftype]:
                if req not in actual_cols:
                    issues.append(
                        f"{f.name}: expected column '{req}' not found.\n"
                        f"    Available columns: {actual_cols}"
                    )
        except Exception as e:
            issues.append(f"{f.name}: could not open file — {e}")

    return len(issues) == 0, issues


def check_db_connection() -> tuple[bool, str]:
    """Verify the database is reachable."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "awards_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            connect_timeout=5,
        )
        conn.close()
        return True, "Connected successfully"
    except Exception as e:
        return False, str(e)


def check_year_not_already_loaded(year: int) -> tuple[bool, str]:
    """Warn if this year is already in the database."""
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=os.getenv("DB_PORT", "5432"),
            dbname=os.getenv("DB_NAME", "awards_db"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
        )
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM classifications WHERE published_year = %s", (year,))
            count = cur.fetchone()[0]
        conn.close()
        if count > 0:
            return False, f"Year {year} already has {count:,} classification rows in the DB (import will upsert/update them)"
        return True, "Year not yet loaded"
    except Exception as e:
        return False, f"Could not check: {e}"

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(year: int):
    print(f"\n{'='*60}")
    print(f"  Awards Data Update — Year {year}")
    print(f"{'='*60}\n")

    all_ok = True

    # --- Check 1: Folder and files ---
    print("[ 1/4 ] Checking Excel files...")
    ok, issues = check_folder(year)
    if ok:
        folder = EXCEL_BASE / str(year)
        files = list(folder.glob("*.xlsx"))
        print(f"        OK — found {len(files)} files in exel/{year}/")
    else:
        all_ok = False
        for issue in issues:
            print(f"        ERROR: {issue}")
        print(f"\n  Fix: Add the missing Excel files to exel/{year}/ then re-run.")
        print(f"  File names must follow: map-{{type}}-export-{year}.xlsx")
        print(f"  Types needed: {', '.join(REQUIRED_FILE_PATTERNS)}")

    # --- Check 2: Column structure ---
    print("\n[ 2/4 ] Checking column structure...")
    ok, issues = check_columns(year)
    if ok:
        print(f"        OK — all required columns present")
    else:
        all_ok = False
        for issue in issues:
            print(f"        ERROR: {issue}")
        print(f"\n  Fix: Check if column names changed in the new files.")
        print(f"  Update etl/importer.py — find the relevant import_xxx() function")
        print(f"  and add the new column name as a fallback in the col() call.")

    # --- Check 3: DB connection ---
    print("\n[ 3/4 ] Checking database connection...")
    ok, msg = check_db_connection()
    if ok:
        print(f"        OK — {msg}")
    else:
        all_ok = False
        print(f"        ERROR: {msg}")
        print(f"\n  Fix: Check your .env file has the correct DB_PASSWORD.")
        print(f"  Also confirm PostgreSQL is running (Windows Services → postgresql-x64-18).")

    # --- Check 4: Already loaded? ---
    print("\n[ 4/4 ] Checking if year already in database...")
    ok, msg = check_year_not_already_loaded(year)
    if ok:
        print(f"        OK — {msg}")
    else:
        print(f"        NOTE: {msg}")
        print(f"        Re-importing is safe — existing rows will be updated.")

    # --- Summary ---
    print(f"\n{'='*60}")
    if not all_ok:
        print("  RESULT: Issues found above must be fixed before importing.")
        print(f"{'='*60}\n")
        sys.exit(1)

    print(f"  All checks passed. Ready to import year {year}.")
    print(f"{'='*60}\n")

    confirm = input(f"  Import year {year} into the database? [y/N]: ").strip().lower()
    if confirm != "y":
        print("  Cancelled. No data was written.")
        sys.exit(0)

    print(f"\n  Running import...")
    from importer import run as do_import
    do_import(years=[year], dry_run=False)

    print(f"\n  Done. Year {year} is now in the database.")
    print(f"  Remember to commit the new Excel files to Git:\n")
    print(f"    git add exel/{year}/")
    print(f"    git commit -m \"Add {year} Award rate data\"")
    print(f"    git push\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add a new year of Award data")
    parser.add_argument("--year", type=int, help="Year to import (e.g. 2026)")
    args = parser.parse_args()

    if args.year:
        year = args.year
    else:
        current = sorted([
            int(d.name) for d in EXCEL_BASE.iterdir()
            if d.is_dir() and d.name.isdigit()
        ])
        suggested = (max(current) + 1) if current else 2026
        try:
            year = int(input(f"  Enter the year to import [{suggested}]: ").strip() or suggested)
        except ValueError:
            print("  Invalid year.")
            sys.exit(1)

    run(year)
