# BackendCalculation

Python backend for calculating and comparing Australian Modern Award rates.
Covers all 4 salary factors — Classification, Wage, Penalty, and Allowances/Expenses —
across historical data from 2015 to present.

Designed to serve a React/JavaScript frontend via a REST API (FastAPI — coming soon).

---

## What This System Does

- Stores all Award rate data (2015–present) in PostgreSQL
- Supports point-in-time lookups: *"What was the rate on 15 March 2022?"*
- Supports year-on-year comparisons: *"How much did rates increase from 2022 to 2024?"*
- Calculates gross pay for a shift including penalties and allowances
- Text search across Awards and classifications by name or keyword
- Importable each year when the Fair Work Commission releases new data
- Audits payslips to detect overpayment, underpayment, or correct pay

---

## Project Structure

```
BackendCalculation/
│
├── awards/                     # Calculation engine
│   ├── models.py               # Data models: Award, Classification, Wage, Penalty, Allowance
│   ├── calculator.py           # Pay calculation logic (all 4 factors)
│   └── __init__.py
│
├── db/
│   ├── schema.sql              # Creates all PostgreSQL tables and indexes
│   └── README.md               # Full database setup and maintenance guide
│
├── etl/
│   ├── importer.py             # Bulk imports all Excel files into PostgreSQL
│   └── add_new_year.py         # Guided tool for adding a new year of data
│
├── exel/                       # Source Excel files from Fair Work Commission
│   ├── 2015/
│   │   ├── map-award-export-2015.xlsx
│   │   ├── map-classification-export-2015.xlsx
│   │   ├── map-expense-allowance-export-2015.xlsx
│   │   ├── map-penalty-export-2015.xlsx
│   │   └── map-wage-allowance-export-2015.xlsx
│   └── 2025/ ...               # One folder per year, same 5 files each year
│
├── api/
│   ├── main.py                 # FastAPI app — CORS, rate limiting, router registration
│   ├── auth.py                 # API key authentication (X-API-Key header)
│   ├── db.py                   # Database connection context manager
│   ├── limiter.py              # Shared rate limiter (Cloudflare IP-aware)
│   └── routes/
│       ├── health.py           # GET /health (no auth)
│       ├── awards.py           # GET /awards, /awards/{code}/classifications, etc.
│       ├── finder.py           # GET /finder
│       ├── calculate.py        # POST /calculate/shift and /period
│       ├── payslips.py         # POST /payslips/generate and /check
│       └── autocomplete.py     # GET /autocomplete/awards and /classifications (typeahead)
│
├── finder/
│   ├── finder.py               # Searches DB and writes resolved Award data to output.json
│   └── input.json              # Edit this with your search terms
│
├── payslips/
│   ├── generator.py            # Generates example payslip JSON files from live DB rates
│   ├── checker.py              # Audits payslips for overpay / underpay / correct
│   ├── PS-2023-001.json        # Jane Smith — correct pay
│   ├── PS-2023-002.json        # Jane Smith — correct pay
│   ├── PS-2023-003.json        # Mark Johnson — underpaid (wrong classification)
│   ├── PS-2024-001.json        # Sarah Chen — overpaid (wrong classification)
│   ├── PS-2024-002.json        # Tom Baker — underpaid (Sunday penalty missing)
│   ├── PS-2024-003.json        # Priya Patel — underpaid (overtime + allowance missing)
│   └── PS-2024-004.json        # James Liu — underpaid (public holiday not applied)
│
├── docs/
│   ├── api-user-guide.md       # Field-by-field API usage guide (for API consumers)
│   └── react-guide.md          # React hooks, components, and integration examples
│
├── example.py                  # Example pay calculation scenarios
├── requirements.txt            # Python dependencies
├── .env.example                # Template for environment variables
└── .gitignore
```

---

## The 4 Salary Factors

| Factor | Table | Description |
|---|---|---|
| **1. Classification** | `classifications` | Employee level within an Award (e.g. Level 1, Level 2) |
| **2. Wage** | `classifications` | Base hourly/weekly rate for each level |
| **3. Penalty** | `penalties` | Multipliers for weekends, public holidays, overtime, night shift |
| **4. Allowance/Expense** | `expense_allowances`, `wage_allowances` | Additional pay for travel, meals, tools, leading hand, etc. |

---

## Quick Start (New Machine)

See [db/README.md](db/README.md) for the full step-by-step guide. Summary:

```bash
# 1. Install PostgreSQL from https://www.postgresql.org/download/windows/
# 2. Add PostgreSQL to PATH (PowerShell as Administrator):
[System.Environment]::SetEnvironmentVariable("Path", $env:Path + ";C:\Program Files\PostgreSQL\18\bin", [System.EnvironmentVariableTarget]::Machine)

# 3. Create database
psql -U postgres -c "CREATE DATABASE awards_db;"

# 4. Clone and install
git clone <repo-url>
cd BackendCalculation
pip install -r requirements.txt

# 5. Configure credentials
copy .env.example .env
# Edit .env and set DB_PASSWORD

# 6. Create tables
python - <<EOF
import os, psycopg2
from dotenv import load_dotenv
load_dotenv()
conn = psycopg2.connect(host=os.getenv("DB_HOST","localhost"), port=os.getenv("DB_PORT","5432"),
    dbname=os.getenv("DB_NAME","awards_db"), user=os.getenv("DB_USER","postgres"), password=os.getenv("DB_PASSWORD",""))
conn.autocommit = True
[conn.cursor().execute(s.strip()) for s in open("db/schema.sql").read().split(";") if s.strip() and not s.strip().startswith("--")]
conn.close()
EOF

# 7. Import all data (2015–present)
python etl/importer.py
```

---

## Adding a New Year

When the Fair Work Commission releases new data (usually July each year):

```bash
# Drop the 5 new Excel files into exel/2026/ then run:
python etl/add_new_year.py
```

The tool checks files, validates columns, confirms DB connection, then asks before writing.
After importing, commit the new files:

```bash
git add exel/2026/
git commit -m "Add 2026 Award rate data"
git push
```

---

## Data Finder

The finder takes search terms as input and resolves them to real Award data — the top matching
Award, Classification, Penalties, and Allowances — and writes the result as structured JSON
ready for use in calculations or comparisons.

**Edit the input file:**

```json
// finder/input.json
{
    "award": "retail",
    "classification": "level 2",
    "date": "2024-03-15",
    "include_penalties": true,
    "include_allowances": true
}
```

**Run:**

```bash
python finder/finder.py
```

**Output** (`finder/output.json`):

```
award               → top match + alternatives with match scores
classification      → top match + alternatives with hourly rates
penalties           → all penalty rows for the resolved classification
expense_allowances  → all expense allowances for the award at that date
wage_allowances     → all wage allowances for the award at that date
```

Handles typos in search terms — `"retial"` still resolves to the Retail Award.
The output file is gitignored (generated data) — the input file is committed.

---

## Payslips

The payslips system generates realistic example payslips from live DB rates and audits them
to detect overpayment, underpayment, or correct pay — useful for testing the calculation
engine and demonstrating real-world compliance checking.

### Generator

`payslips/generator.py` queries the live database for real Award rates and builds fully
structured payslip JSON files, each containing:

- Employee details (name, employment type, classification level)
- Award and classification resolved from the DB
- Shift-by-shift breakdown (hours, day type, penalty multiplier, allowances applied)
- A `calculated` block showing what the employee *should* have been paid per shift
- A `paid` block showing what was *actually* paid (may be correct or contain a deliberate error)
- An `audit` block with `calculated_gross`, `paid_gross`, `variance`, `variance_pct`, `status`, and `issues`

```bash
python payslips/generator.py
```

Regenerates all 7 payslip JSON files from the current database. Run this after importing
new rate data to keep the examples current.

### Checker

`payslips/checker.py` reads payslip JSON files and reports on each one:

```bash
python payslips/checker.py                          # check all payslips (detailed)
python payslips/checker.py --summary                # summary table only
python payslips/checker.py --file PS-2024-002.json  # check a single payslip
```

**Example summary output:**

```
  =================================================================
                      PAYSLIP AUDIT SUMMARY
  =================================================================
  ID               Employee         Period                      Variance  Status
  -----------------------------------------------------------------
  PS-2023-001      Jane Smith       2023-07-03 → 2023-07-09      +$0.00   OK
  PS-2023-002      Jane Smith       2023-07-10 → 2023-07-16      +$0.00   OK
  PS-2023-003      Mark Johnson     2023-08-07 → 2023-08-13     -$31.20   UNDERPAID
  PS-2024-001      Sarah Chen       2024-03-04 → 2024-03-10     +$21.82   OVERPAID
  PS-2024-002      Tom Baker        2024-03-11 → 2024-03-17    -$202.32   UNDERPAID
  PS-2024-003      Priya Patel      2024-06-03 → 2024-06-09    -$137.29   UNDERPAID
  PS-2024-004      James Liu        2024-06-10 → 2024-06-16    -$256.80   UNDERPAID
  -----------------------------------------------------------------
  Total: 7  |  Correct: 2  |  Underpaid: 4  |  Overpaid: 1
  Net variance across all payslips: -$605.79
  =================================================================
```

### Pre-generated Example Files

Seven payslip files are included covering a range of correct and error scenarios:

| File | Employee | Scenario | Status | Variance |
|---|---|---|---|---|
| `PS-2023-001.json` | Jane Smith | Level 2, standard week | Correct | $0.00 |
| `PS-2023-002.json` | Jane Smith | Level 2, standard week | Correct | $0.00 |
| `PS-2023-003.json` | Mark Johnson | Level 3 employee paid at Level 2 rate | Underpaid | −$31.20 |
| `PS-2024-001.json` | Sarah Chen | Level 1 employee paid at Level 2 rate | Overpaid | +$21.82 |
| `PS-2024-002.json` | Tom Baker | Sunday penalty applied at ordinary rate (1.0×) | Underpaid | −$202.32 |
| `PS-2024-003.json` | Priya Patel | Overtime paid at flat rate + meal allowances missed | Underpaid | −$137.29 |
| `PS-2024-004.json` | James Liu | Public holiday shift paid at ordinary weekday rate | Underpaid | −$256.80 |

### Payslip JSON Structure

```json
{
  "payslip_id": "PS-2024-002",
  "employee": {
    "name": "Tom Baker",
    "employment_type": "full_time",
    "classification_level": 2
  },
  "award": { "code": "MA000004", "name": "General Retail Industry Award 2020" },
  "pay_period": { "start": "2024-03-11", "end": "2024-03-17" },
  "shifts": [
    {
      "date": "2024-03-11",
      "day_type": "weekday",
      "hours": 7.6,
      "penalty_multiplier": 1.0,
      "allowances": [],
      "calculated_pay": 190.93,
      "paid_pay": 190.93
    }
  ],
  "calculated": { "gross": 1234.56, "breakdown": { ... } },
  "paid":       { "gross": 1032.24, "notes": "Sunday penalty not applied" },
  "audit": {
    "calculated_gross": 1234.56,
    "paid_gross":       1032.24,
    "variance":         -202.32,
    "variance_pct":     -16.39,
    "status":           "underpaid",
    "issues":           ["Sunday shifts paid at 1.0x ordinary rate instead of 2.0x"]
  }
}
```

---

## REST API

The FastAPI layer exposes all backend functionality over HTTP. Designed to sit behind
Cloudflare, which handles HTTPS and DDoS protection.

### Setup

Add two new values to your `.env` file:

```bash
# Generate a strong key:
python -c "import secrets; print(secrets.token_hex(32))"
```

```ini
API_KEY=your-generated-key-here
ALLOWED_ORIGINS=https://yourdomain.com
```

### Running

```bash
python -m uvicorn api.main:app --reload --port 8000
```

Interactive docs (Swagger UI) are available at `http://localhost:8000/docs` while running.

### Authentication

Every endpoint (except `/health`) requires the `X-API-Key` header:

```
X-API-Key: your-generated-key-here
```

### Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | API + DB status — **no auth required** |
| `GET` | `/awards?search=retail` | Search awards by name (typo-tolerant) |
| `GET` | `/awards/{code}/classifications?search=level+2&date=2024-03-15` | Classifications for an award |
| `GET` | `/awards/{code}/penalties?date=2024-03-15` | Penalty rates for an award |
| `GET` | `/awards/{code}/allowances?date=2024-03-15` | Allowances for an award |
| `GET` | `/finder?award=retail&classification=level+2&date=2024-03-15` | Full data bundle in one call |
| `POST` | `/calculate/shift` | Calculate gross pay for a single shift |
| `POST` | `/calculate/period` | Calculate total pay across a full pay period |
| `POST` | `/payslips/generate` | Generate a payslip from shift inputs using live DB rates |
| `POST` | `/payslips/check` | Audit an existing payslip JSON for overpay/underpay |
| `GET` | `/awards/{code}/compare?year_from=2022&year_to=2024` | Year-on-year rate comparison |
| `GET` | `/autocomplete/awards?q=ret` | Live award name search (per keystroke) |
| `GET` | `/autocomplete/classifications?award=MA000004&q=lev` | Live classification search (per keystroke) |

### Autocomplete / Typeahead

The autocomplete endpoints are designed to power a live search bar — call them on every keystroke.
Results are ranked by closeness to what the user has typed so far:

- **1–2 chars** typed → prefix match only (fast, low noise)
- **3+ chars** typed → prefix + fuzzy combined (handles typos like `retial` → Retail Award)

**Typical two-step search bar flow:**
```
User types in award box  →  GET /autocomplete/awards?q={input}              → dropdown
User selects an award    →  store award_code (e.g. MA000004)
User types in class box  →  GET /autocomplete/classifications
                               ?award=MA000004&q={input}                     → dropdown
User selects a class     →  you have the hourly rate and classification level
```

### Security

| Layer | What it does |
|---|---|
| **Cloudflare** | HTTPS termination, DDoS protection, WAF |
| **API Key** | `X-API-Key` header required on all routes |
| **CORS** | Only your domain(s) in `ALLOWED_ORIGINS` can call the API |
| **Rate limiting** | 60 req/min (awards), 30 req/min (finder/payslips), 120 req/min (autocomplete) per IP |
| **Input validation** | All query params validated by FastAPI/Pydantic before hitting the DB |
| **Parameterised queries** | All SQL uses `%s` placeholders — no SQL injection possible |

### Example calls

```bash
# Health check (no key needed)
curl https://api.yourdomain.com/health

# Live autocomplete — award name as user types
curl -H "X-API-Key: your-key" "https://api.yourdomain.com/autocomplete/awards?q=ret"

# Live autocomplete — classification within a chosen award
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/autocomplete/classifications?award=MA000004&q=lev"

# Full finder bundle
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/finder?award=retail&classification=level+2&date=2024-03-15"

# Audit a payslip
curl -X POST -H "X-API-Key: your-key" -H "Content-Type: application/json" \
  -d @payslips/PS-2024-002.json \
  "https://api.yourdomain.com/payslips/check"
```

### Further Reading

| Guide | Description |
|---|---|
| [api/README.md](api/README.md) | Full endpoint reference with request/response examples |
| [docs/api-user-guide.md](docs/api-user-guide.md) | Field-by-field guide for API consumers — what to send and what you get back |
| [docs/react-guide.md](docs/react-guide.md) | React hooks, components, and a ready-to-use integration |
| [db/README.md](db/README.md) | Database setup, annual maintenance checklist, and key rotation |

---

## Running the Example

```bash
python example.py
```

Calculates pay for 4 scenarios using the Retail Award — weekday ordinary time,
Sunday shift with travel allowance, overtime with multiple allowances, and a pay period summary.

---

## Search Capabilities

Three levels of search are supported:

| Type | Handles | Example |
|---|---|---|
| **ILIKE** | Partial match, case insensitive | `retai` finds `retail` |
| **Full-text (FTS)** | Keywords, word stemming | `mine` finds `mining` |
| **Fuzzy (pg_trgm)** | Typos, misspellings | `retial` finds `retail` |

All search indexes are defined in `db/schema.sql` and deploy automatically with the schema — no manual setup needed on any environment.

## Key Database Queries

```sql
-- Partial name search (case insensitive)
SELECT award_code, name FROM awards WHERE name ILIKE '%retail%' GROUP BY 1,2;

-- Fuzzy / typo-tolerant search (handles misspellings)
SELECT award_code, name, ROUND(word_similarity('retial', name)::numeric, 2) AS score
FROM awards
WHERE word_similarity('retial', name) > 0.4
GROUP BY award_code, name ORDER BY score DESC;

-- Get all classifications for an award in a specific year
SELECT classification, classification_level, calculated_rate
FROM classifications
WHERE award_code = 'MA000004' AND published_year = 2024
ORDER BY classification_level;

-- Point-in-time rate lookup
SELECT classification, calculated_rate
FROM classifications
WHERE award_code = 'MA000004'
  AND operative_from <= '2022-03-15'
  AND (operative_to >= '2022-03-15' OR operative_to IS NULL);

-- Compare rates across two years
SELECT a.classification,
       a.calculated_rate AS rate_2022,
       b.calculated_rate AS rate_2024,
       ROUND(b.calculated_rate - a.calculated_rate, 4) AS increase
FROM classifications a
JOIN classifications b ON a.classification_fixed_id = b.classification_fixed_id
WHERE a.published_year = 2022 AND b.published_year = 2024
  AND a.award_code = 'MA000004';
```

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pandas` | 2.2.3 | Reading Excel files |
| `openpyxl` | 3.1.5 | Excel file engine for pandas |
| `psycopg2-binary` | 2.9.10 | PostgreSQL driver |
| `python-dotenv` | 1.0.1 | Load credentials from `.env` |
| `sqlalchemy` | 2.0.36 | ORM (used by API layer) |
| `slowapi` | 0.1.9 | Rate limiting middleware for FastAPI |
| `fastapi` | 0.115.6 | REST API framework |
| `uvicorn` | 0.32.1 | ASGI server for FastAPI |

Install all: `pip install -r requirements.txt`

---

## Data Source

Excel files exported from the Fair Work Commission's
[Pay and Conditions Tool (PACT)](https://www.fairwork.gov.au/pay-and-conditions/pay-calculator).
Updated annually each July following the Annual Wage Review.

---

## Roadmap

- [x] Data models (Classification, Wage, Penalty, Allowance)
- [x] Pay calculation engine
- [x] PostgreSQL schema with temporal (point-in-time) support
- [x] ETL importer for all years (2015–2025)
- [x] Full-text and ILIKE search indexes
- [x] Yearly update tool
- [x] Award Data Finder (search → structured JSON output)
- [x] Payslip generation with real Award rates
- [x] Payslip checker — detects overpay / underpay / correct
- [x] FastAPI REST endpoints with API key auth, CORS, and rate limiting
- [x] Pay calculator API (single shift + pay period)
- [x] Payslip generator API (from shift inputs + live DB rates)
- [x] Historical comparison API (year-on-year rate comparison)
- [x] Live autocomplete search (per-keystroke award + classification)
- [x] API consumer guide (field-by-field request/response reference)
- [x] React integration guide (hooks, components, example app)
- [ ] React frontend (build the actual UI)
