"""
ETL Importer — Australian Modern Awards Excel → PostgreSQL

Reads all yearly Excel files from the /exel folder and loads them
into PostgreSQL. Handles column name inconsistencies across years
automatically (case differences, typos, etc.)

Usage:
    python etl/importer.py                  # import all years
    python etl/importer.py --year 2024      # import one year only
    python etl/importer.py --dry-run        # print stats, no DB write
"""

import os
import sys
import argparse

# Fix Windows terminal encoding for Unicode characters in award names
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------

def get_connection():
    return psycopg2.connect(
        host     = os.getenv("DB_HOST", "localhost"),
        port     = os.getenv("DB_PORT", "5432"),
        dbname   = os.getenv("DB_NAME", "awards_db"),
        user     = os.getenv("DB_USER", "postgres"),
        password = os.getenv("DB_PASSWORD", ""),
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Lowercase all column headers and strip whitespace.
    Handles inconsistencies like 'OperativeFrom' vs 'operativeFrom'.
    """
    df.columns = [c.strip().lower() for c in df.columns]
    return df


def to_date(value):
    """Convert a value to a Python date, or None if missing."""
    if pd.isna(value) or value is None:
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def to_int(value):
    """Convert a value to int, or None if missing/non-numeric."""
    if pd.isna(value) or value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def to_float(value):
    """Convert a value to float, or None if missing."""
    if pd.isna(value) or value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def to_bool(value):
    if pd.isna(value) or value is None:
        return False
    return bool(int(value))


def col(df: pd.DataFrame, *names):
    """
    Get the first matching column from a list of candidate names.
    Handles typos and historical naming differences.
    """
    for name in names:
        if name.lower() in df.columns:
            return df[name.lower()]
    return pd.Series([None] * len(df))


def filter_detail_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Remove heading rows — only keep actual data rows."""
    if "isheading" in df.columns:
        df = df[df["isheading"] == 0]
    if "type" in df.columns:
        df = df[df["type"].str.strip().str.lower() != "heading"]
    return df.reset_index(drop=True)

# ---------------------------------------------------------------------------
# Per-file importers
# ---------------------------------------------------------------------------

def dedup(rows: list, key_indices: tuple) -> list:
    """Remove duplicate rows by conflict key, keeping the last occurrence."""
    seen = {}
    for row in rows:
        key = tuple(row[i] for i in key_indices)
        seen[key] = row
    return list(seen.values())


def import_awards(df: pd.DataFrame, year: int, cur) -> int:
    df = normalise_columns(df)

    rows = []
    for _, row in df.iterrows():
        rows.append((
            to_int(row.get("awardfixedid")),
            str(row.get("awardcode", "") or "").strip(),
            str(row.get("name", "") or "").strip(),
            to_date(row.get("awardoperativefrom")),
            to_date(row.get("awardoperativeto")),
            year,
        ))

    rows = dedup([r for r in rows if r[0] is not None and r[1]], (0, 5))  # award_fixed_id, year

    execute_values(cur, """
        INSERT INTO awards
            (award_fixed_id, award_code, name, operative_from, operative_to, published_year)
        VALUES %s
        ON CONFLICT (award_fixed_id, published_year) DO UPDATE SET
            name           = EXCLUDED.name,
            operative_from = EXCLUDED.operative_from,
            operative_to   = EXCLUDED.operative_to
    """, rows)

    return len(rows)


def import_classifications(df: pd.DataFrame, year: int, cur) -> int:
    df = normalise_columns(df)
    df = filter_detail_rows(df)

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("awardcode", "") or "").strip(),
            to_int(row.get("classificationfixedid")),
            year,
            str(row.get("classification", "") or "").strip() or None,
            to_int(row.get("classificationlevel")),
            str(row.get("parentclassificationname", "") or "").strip() or None,
            str(row.get("clauses", "") or "").strip() or None,
            to_float(row.get("baserate")),
            str(row.get("baseratetype", "") or "").strip() or None,
            to_float(row.get("calculatedrate")),
            str(row.get("calculatedratetype", "") or "").strip() or None,
            to_bool(row.get("calculatedincludesallpurpose")),
            to_date(row.get("operativefrom")),
            to_date(row.get("operativeto")),
        ))

    rows = dedup([r for r in rows if r[1] is not None and r[0]], (1, 2))  # classification_fixed_id, year

    execute_values(cur, """
        INSERT INTO classifications
            (award_code, classification_fixed_id, published_year,
             classification, classification_level, parent_classification_name,
             clause, base_rate, base_rate_type,
             calculated_rate, calculated_rate_type,
             calculated_includes_all_purpose,
             operative_from, operative_to)
        VALUES %s
        ON CONFLICT (classification_fixed_id, published_year) DO UPDATE SET
            classification              = EXCLUDED.classification,
            classification_level        = EXCLUDED.classification_level,
            base_rate                   = EXCLUDED.base_rate,
            calculated_rate             = EXCLUDED.calculated_rate,
            operative_from              = EXCLUDED.operative_from,
            operative_to                = EXCLUDED.operative_to
    """, rows)

    return len(rows)


def import_penalties(df: pd.DataFrame, year: int, cur) -> int:
    df = normalise_columns(df)
    df = filter_detail_rows(df)

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("awardcode", "") or "").strip(),
            to_int(row.get("penaltyfixedid")),
            year,
            str(row.get("classification", "") or "").strip() or None,
            to_int(row.get("classificationlevel")),
            str(row.get("parentclassificationname", "") or "").strip() or None,
            str(row.get("clauses", "") or "").strip() or None,
            str(row.get("penaltydescription", "") or "").strip() or None,
            str(row.get("employeeratetypecode", "") or "").strip() or None,
            to_float(row.get("rate")),
            str(row.get("penaltyrateunit", "") or "").strip() or None,
            to_float(row.get("penaltycalculatedvalue")),
            to_bool(row.get("calculatedincludesallpurpose")),
            to_date(row.get("operativefrom")),
            to_date(row.get("operativeto")),
        ))

    rows = dedup([r for r in rows if r[1] is not None and r[0]], (1, 2))  # penalty_fixed_id, year

    execute_values(cur, """
        INSERT INTO penalties
            (award_code, penalty_fixed_id, published_year,
             classification, classification_level, parent_classification_name,
             clause, penalty_description, employee_rate_type_code,
             rate, penalty_rate_unit, penalty_calculated_value,
             calculated_includes_all_purpose,
             operative_from, operative_to)
        VALUES %s
        ON CONFLICT (penalty_fixed_id, published_year) DO UPDATE SET
            classification           = EXCLUDED.classification,
            penalty_description      = EXCLUDED.penalty_description,
            rate                     = EXCLUDED.rate,
            penalty_calculated_value = EXCLUDED.penalty_calculated_value,
            operative_from           = EXCLUDED.operative_from,
            operative_to             = EXCLUDED.operative_to
    """, rows)

    return len(rows)


def import_expense_allowances(df: pd.DataFrame, year: int, cur) -> int:
    df = normalise_columns(df)
    df = filter_detail_rows(df)

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("awardcode", "") or "").strip(),
            to_int(row.get("expenseallowancefixedid")),
            year,
            str(row.get("allowance", "") or "").strip() or None,
            str(row.get("parentallowance", "") or "").strip() or None,
            str(row.get("clauses", "") or "").strip() or None,
            to_float(row.get("allowanceamount")),
            str(row.get("paymentfrequency", "") or "").strip() or None,
            to_bool(row.get("isallpurpose")),
            to_date(row.get("operativefrom")),
            to_date(row.get("operativeto")),
        ))

    rows = dedup([r for r in rows if r[1] is not None and r[0]], (1, 2))  # expense_allowance_fixed_id, year

    execute_values(cur, """
        INSERT INTO expense_allowances
            (award_code, expense_allowance_fixed_id, published_year,
             allowance, parent_allowance, clause,
             allowance_amount, payment_frequency, is_all_purpose,
             operative_from, operative_to)
        VALUES %s
        ON CONFLICT (expense_allowance_fixed_id, published_year) DO UPDATE SET
            allowance         = EXCLUDED.allowance,
            allowance_amount  = EXCLUDED.allowance_amount,
            payment_frequency = EXCLUDED.payment_frequency,
            operative_from    = EXCLUDED.operative_from,
            operative_to      = EXCLUDED.operative_to
    """, rows)

    return len(rows)


def import_wage_allowances(df: pd.DataFrame, year: int, cur) -> int:
    df = normalise_columns(df)
    df = filter_detail_rows(df)

    rows = []
    for _, row in df.iterrows():
        rows.append((
            str(row.get("awardcode", "") or "").strip(),
            to_int(row.get("wageallowancefixedid")),
            year,
            str(row.get("allowance", "") or "").strip() or None,
            str(row.get("parentallowance", "") or "").strip() or None,
            str(row.get("clauses", "") or "").strip() or None,
            to_float(row.get("rate")),
            to_float(row.get("baserate")),
            str(row.get("rateunit", "") or "").strip() or None,
            to_float(row.get("allowanceamount")),
            str(row.get("paymentfrequency", "") or "").strip() or None,
            to_bool(row.get("isallpurpose")),
            to_date(row.get("operativefrom")),
            to_date(row.get("operativeto")),
        ))

    rows = dedup([r for r in rows if r[1] is not None and r[0]], (1, 2))  # wage_allowance_fixed_id, year

    execute_values(cur, """
        INSERT INTO wage_allowances
            (award_code, wage_allowance_fixed_id, published_year,
             allowance, parent_allowance, clause,
             rate, base_rate, rate_unit,
             allowance_amount, payment_frequency, is_all_purpose,
             operative_from, operative_to)
        VALUES %s
        ON CONFLICT (wage_allowance_fixed_id, published_year) DO UPDATE SET
            allowance         = EXCLUDED.allowance,
            rate              = EXCLUDED.rate,
            base_rate         = EXCLUDED.base_rate,
            allowance_amount  = EXCLUDED.allowance_amount,
            payment_frequency = EXCLUDED.payment_frequency,
            operative_from    = EXCLUDED.operative_from,
            operative_to      = EXCLUDED.operative_to
    """, rows)

    return len(rows)

# ---------------------------------------------------------------------------
# File type detection — handles inconsistent naming across years
# ---------------------------------------------------------------------------

FILE_TYPES = {
    "award":             import_awards,
    "classification":    import_classifications,
    "penalty":           import_penalties,
    "expense-allowance": import_expense_allowances,
    "expense_allowance": import_expense_allowances,
    "wage-allowance":    import_wage_allowances,
    "wage_allowance":    import_wage_allowances,
}

def detect_file_type(filename: str):
    """Match filename to a known type regardless of year suffix or minor variations."""
    name = filename.lower().replace("map-", "").replace("-export", "").replace("_export", "")
    # strip year and extension
    for part in name.split("-") + name.split("_"):
        for ftype in FILE_TYPES:
            if ftype.replace("-", "") in part.replace("-", ""):
                return ftype
    return None

# ---------------------------------------------------------------------------
# Main import loop
# ---------------------------------------------------------------------------

def import_year(year: int, excel_base: Path, cur, dry_run: bool):
    year_path = excel_base / str(year)
    if not year_path.exists():
        print(f"  [SKIP] No folder found for {year}")
        return

    print(f"\n--- Year {year} ---")

    for xlsx_file in sorted(year_path.glob("*.xlsx")):
        ftype = detect_file_type(xlsx_file.stem)
        if ftype is None:
            print(f"  [UNKNOWN] {xlsx_file.name} — skipping")
            continue

        try:
            df = pd.read_excel(xlsx_file)
            if dry_run:
                print(f"  [DRY RUN] {xlsx_file.name} → {ftype} ({len(df)} rows)")
                continue

            # Savepoint per file — an error here won't abort the whole transaction
            cur.execute("SAVEPOINT sp_file")
            importer_fn = FILE_TYPES[ftype]
            count = importer_fn(df, year, cur)
            cur.execute("RELEASE SAVEPOINT sp_file")
            print(f"  [OK] {xlsx_file.name} → {ftype}: {count} rows imported")

        except Exception as e:
            cur.execute("ROLLBACK TO SAVEPOINT sp_file")
            print(f"  [ERROR] {xlsx_file.name}: {e}")


def run(years: list[int] | None = None, dry_run: bool = False):
    excel_base = Path(__file__).parent.parent / "exel"

    available_years = sorted([
        int(d.name) for d in excel_base.iterdir()
        if d.is_dir() and d.name.isdigit()
    ])

    target_years = years if years else available_years
    print(f"Importing years: {target_years}")
    print(f"Dry run: {dry_run}")

    if dry_run:
        for year in target_years:
            import_year(year, excel_base, cur=None, dry_run=True)
        return

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                for year in target_years:
                    import_year(year, excel_base, cur, dry_run=False)
        print("\n✓ Import complete — all changes committed.")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import Award Excel files into PostgreSQL")
    parser.add_argument("--year", type=int, help="Import a single year only (e.g. --year 2024)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be imported without writing to DB")
    args = parser.parse_args()

    years = [args.year] if args.year else None
    run(years=years, dry_run=args.dry_run)
