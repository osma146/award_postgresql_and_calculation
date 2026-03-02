# Database Setup & Maintenance Guide

This document covers everything needed to set up, run, and maintain the
Awards database — from a brand new machine to adding a new year of data.

---

## Prerequisites

- Python 3.11 or later
- PostgreSQL 16 or later ([postgresql.org/download](https://www.postgresql.org/download/windows/))
- Git

---

## Folder Structure

```
BackendCalculation/
├── db/
│   ├── schema.sql          ← Creates all database tables (run once)
│   └── README.md           ← This file
├── etl/
│   └── importer.py         ← Reads Excel files and loads into DB
├── exel/
│   ├── 2015/               ← One folder per year
│   │   ├── map-award-export-2015.xlsx
│   │   ├── map-classification-export-2015.xlsx
│   │   ├── map-expense-allowance-export-2015.xlsx
│   │   ├── map-penalty-export-2015.xlsx
│   │   └── map-wage-allowance-export-2015.xlsx
│   └── 2025/  ...
├── awards/                 ← Python calculation engine
├── .env                    ← Your local DB credentials (never in Git)
├── .env.example            ← Template showing required variables
└── requirements.txt        ← Python dependencies
```

---

## Setup From Scratch (New Machine)

Follow these steps in order on any new machine.

### Step 1 — Install PostgreSQL

Download and run the Windows installer from:
https://www.postgresql.org/download/windows/

During install:
- Keep default port: `5432`
- Set a password for the `postgres` user — **write it down**
- Leave all other options as default

After install, add PostgreSQL to your PATH.
Open PowerShell **as Administrator** and run:

```powershell
[System.Environment]::SetEnvironmentVariable(
  "Path",
  $env:Path + ";C:\Program Files\PostgreSQL\18\bin",
  [System.EnvironmentVariableTarget]::Machine
)
```

Close and reopen your terminal. Verify with:

```bash
psql --version
```

---

### Step 2 — Clone the Repository

```bash
git clone <your-repo-url>
cd BackendCalculation
```

---

### Step 3 — Install Python Dependencies

```bash
pip install -r requirements.txt
```

---

### Step 4 — Create the Database

```bash
psql -U postgres -c "CREATE DATABASE awards_db;"
```

---

### Step 5 — Create Tables (Run Schema)

```bash
psql -U postgres -d awards_db -f db/schema.sql
```

You should see output like:
```
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE TABLE
CREATE INDEX
...
```

---

### Step 6 — Configure Environment

Copy the example env file and fill in your password:

```bash
copy .env.example .env
```

Open `.env` and set your PostgreSQL password:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=awards_db
DB_USER=postgres
DB_PASSWORD=your_password_here
```

---

### Step 7 — Import All Excel Data

This loads all years (2015–present) into the database in one command:

```bash
python etl/importer.py
```

Expected output:
```
Importing years: [2015, 2016, 2017, ... 2025]

--- Year 2015 ---
  [OK] map-award-export-2015.xlsx → award: 155 rows imported
  [OK] map-classification-export-2015.xlsx → classification: 8772 rows imported
  ...

✓ Import complete — all changes committed.
```

This takes approximately 2–5 minutes for all years.

---

### Step 8 — Verify the Import

Connect to the database and check row counts:

```bash
psql -U postgres -d awards_db -c "
  SELECT 'awards'            AS table_name, COUNT(*) FROM awards
  UNION ALL
  SELECT 'classifications',               COUNT(*) FROM classifications
  UNION ALL
  SELECT 'penalties',                     COUNT(*) FROM penalties
  UNION ALL
  SELECT 'expense_allowances',            COUNT(*) FROM expense_allowances
  UNION ALL
  SELECT 'wage_allowances',               COUNT(*) FROM wage_allowances;
"
```

Expected (approximate):

| table               | count   |
|---------------------|---------|
| awards              | 1,705   |
| classifications     | 154,000 |
| penalties           | 556,000 |
| expense_allowances  | 13,000  |
| wage_allowances     | 20,000  |

---

## Adding a New Year of Data

Each year the Fair Work Commission releases updated Excel files (usually in July).
Follow these steps to add the new year without touching existing data.

### Step 1 — Add the Excel Files

Create a new folder under `exel/` named with the year:

```
exel/
└── 2026/
    ├── map-award-export-2026.xlsx
    ├── map-classification-export-2026.xlsx
    ├── map-expense-allowance-export-2026.xlsx
    ├── map-penalty-export-2026.xlsx
    └── map-wage-allowance-export-2026.xlsx
```

File naming must follow the pattern: `map-{type}-export-{year}.xlsx`
Types: `award`, `classification`, `expense-allowance`, `penalty`, `wage-allowance`

### Step 2 — Dry Run First (Recommended)

Check that the new files are detected and readable before writing to the DB:

```bash
python etl/importer.py --year 2026 --dry-run
```

You should see row counts with no errors. If a file has a different column
name or format, an `[ERROR]` will appear — see Troubleshooting below.

### Step 3 — Import the New Year

```bash
python etl/importer.py --year 2026
```

This only touches the new year — all existing data is untouched.
Re-running the same year is safe: rows are upserted (updated if already exist).

### Step 4 — Commit the New Files

```bash
git add exel/2026/
git commit -m "Add 2026 Award rate data"
git push
```

### Step 5 — Run on Production

SSH into the production server (or trigger your deployment pipeline) and run:

```bash
python etl/importer.py --year 2026
```

---

## Search Types

Three levels of text search are available, all set up automatically by `schema.sql`:

| Type | Query syntax | What it handles |
|---|---|---|
| Partial match | `WHERE name ILIKE '%retail%'` | Partial words, case insensitive |
| Full-text | `WHERE to_tsvector('english', name) @@ to_tsquery('english', 'retail')` | Keywords, word stemming |
| Fuzzy / typo | `WHERE word_similarity('retial', name) > 0.4` | Misspellings, transposed letters |

The fuzzy search uses the `pg_trgm` PostgreSQL extension (enabled automatically in `schema.sql`).
It is part of every standard PostgreSQL install — no extra software needed.

---

## Useful Database Commands

```bash
# Connect to the database interactively
psql -U postgres -d awards_db

# Check what years are loaded
psql -U postgres -d awards_db -c "SELECT DISTINCT published_year FROM classifications ORDER BY 1;"

# Look up rates for a specific award and year
psql -U postgres -d awards_db -c "
  SELECT classification, classification_level, calculated_rate, operative_from, operative_to
  FROM classifications
  WHERE award_code = 'MA000004'
    AND published_year = 2024
  ORDER BY classification_level;
"

# Point-in-time lookup — what were the rates on a specific date?
psql -U postgres -d awards_db -c "
  SELECT classification, calculated_rate
  FROM classifications
  WHERE award_code = 'MA000004'
    AND operative_from <= '2022-03-15'
    AND (operative_to >= '2022-03-15' OR operative_to IS NULL)
  ORDER BY classification_level;
"
```

---

## Troubleshooting

### `psql: command not found`
PostgreSQL is not in your PATH. Re-run Step 1 (PATH fix) and open a new terminal.

### `could not connect to server`
PostgreSQL service is not running. Open Windows Services and start `postgresql-x64-18`.
Or run: `pg_ctl start -D "C:\Program Files\PostgreSQL\18\data"`

### `database "awards_db" does not exist`
Re-run Step 4 to create the database.

### `[ERROR] map-xxx-export-2026.xlsx: ...column not found`
The new year's file has a renamed column. Open the file, check the header row,
and add the new column name as a fallback in `etl/importer.py` in the relevant
`import_xxx` function using the `col(df, "old_name", "new_name")` helper.

### Re-running the schema on an existing database
The schema uses `CREATE TABLE IF NOT EXISTS` — it is safe to re-run at any time.
It will not drop or modify existing data.

---

## Production Deployment Notes

- Never commit `.env` to Git — it contains your database password
- On the production server, set environment variables directly or use a secrets manager
- The `DB_PASSWORD` environment variable overrides `.env` if both are set
- All imports use upsert (`ON CONFLICT ... DO UPDATE`) — re-running is always safe
