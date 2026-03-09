# API User Guide

This guide is for developers **calling** the API — what data to send, what fields to include,
and what you get back. It assumes the API is already running and you have an API key.

---

## Before You Start

Every request (except `/health`) needs this header:

```
X-API-Key: your-api-key-here
```

All request bodies use `Content-Type: application/json`.
All dates use `YYYY-MM-DD` format.

---

## Quick Reference

| What you want | Endpoint |
|---|---|
| Search for an award by name | `GET /awards?search=retail` |
| Live search as user types | `GET /autocomplete/awards?q=ret` |
| Get hourly rate for a level | `GET /awards/{code}/classifications?search=level+2&date=2024-03-15` |
| Get penalty rates (weekend etc) | `GET /awards/{code}/penalties?date=2024-03-15` |
| Get allowances | `GET /awards/{code}/allowances?date=2024-03-15` |
| Everything in one call | `GET /finder?award=retail&classification=level+2&date=2024-03-15` |
| Calculate one shift | `POST /calculate/shift` |
| Calculate a pay period | `POST /calculate/period` |
| Generate a payslip | `POST /payslips/generate` |
| Check an existing payslip | `POST /payslips/check` |
| Compare rates 2022 vs 2024 | `GET /awards/{code}/compare?year_from=2022&year_to=2024` |
| Check API is running | `GET /health` |

---

## Award Codes

You need an award code to look up rates. Get one by searching first:

```
GET /awards?search=retail
```

Common codes:
| Award | Code |
|---|---|
| General Retail Industry Award 2020 | `MA000004` |
| Hospitality Industry (General) Award 2020 | `MA000009` |
| Fast Food Industry Award 2010 | `MA000003` |
| Clerks—Private Sector Award 2020 | `MA000002` |

If you don't know the code, search by name — it's typo-tolerant.

---

## Searching for an Award

### `GET /awards`

| Field | Type | Required | Notes |
|---|---|---|---|
| `search` | string | Yes | Min 2 chars. Handles typos. |
| `top` | integer | No | Max results. Default 5, max 20. |

```bash
GET /awards?search=retail&top=5
```

**Response — array of award matches:**

| Field | Type | Description |
|---|---|---|
| `award_code` | string | Unique code — use this in other endpoints |
| `name` | string | Full award name |
| `match_score` | float | How close the match is (0–1). 1.0 = exact match. |

```json
[
  { "award_code": "MA000004", "name": "General Retail Industry Award 2020", "match_score": 1.0 },
  { "award_code": "MA000059", "name": "Retail Award 2010",                   "match_score": 0.78 }
]
```

---

## Getting Classifications (Hourly Rates)

### `GET /awards/{code}/classifications`

| Field | Type | Required | Notes |
|---|---|---|---|
| `search` | string | Yes | Level name or number. e.g. `level 2` or `2` |
| `date` | date | No | `YYYY-MM-DD`. Omit for latest rates. |
| `top` | integer | No | Default 5. |

```bash
GET /awards/MA000004/classifications?search=level+2&date=2024-03-15
```

**Response — array of classification matches:**

| Field | Type | Description |
|---|---|---|
| `classification_fixed_id` | integer | Stable ID — use for year-on-year comparison |
| `classification` | string | Full classification name |
| `classification_level` | integer | Numeric level |
| `base_rate_weekly` | float | Weekly base wage |
| `base_rate_type` | string | Usually `"weekly"` |
| `calculated_rate_hourly` | float | **Hourly rate — this is what you use for calculations** |
| `calculated_rate_type` | string | Usually `"hourly"` |
| `operative_from` | date | Date this rate started |
| `operative_to` | date or null | Date this rate ended. `null` = currently active |
| `match_score` | float | How well the name matched your search |

```json
[
  {
    "classification_fixed_id": 12342,
    "classification": "Retail Employee Level 2",
    "classification_level": 2,
    "base_rate_weekly": 886.30,
    "base_rate_type": "weekly",
    "calculated_rate_hourly": 23.32,
    "calculated_rate_type": "hourly",
    "operative_from": "2023-07-01",
    "operative_to": null,
    "match_score": 0.9
  }
]
```

---

## Getting Penalty Rates

### `GET /awards/{code}/penalties`

Penalties are multipliers applied on top of the base rate for weekends, public holidays,
overtime, etc.

| Field | Type | Required | Notes |
|---|---|---|---|
| `classification` | string | No | Filter by classification name. Omit for all. |
| `date` | date | No | Point-in-time date. Omit for latest. |

```bash
GET /awards/MA000004/penalties?date=2024-03-15&classification=level+2
```

**Response — array of penalty rules:**

| Field | Type | Description |
|---|---|---|
| `penalty_fixed_id` | integer | Stable ID |
| `description` | string | What this penalty applies to (e.g. `"Sunday"`, `"Overtime — first 2 hours"`) |
| `employee_rate_type` | string | Employee type this applies to |
| `rate` | float | Penalty as a percentage (e.g. `200.0` = 200%) |
| `rate_unit` | string | Usually `"percent"` |
| `calculated_value` | float | **Multiplier to apply to base rate** (e.g. `2.0` for Sunday) |
| `clause` | string | Award clause reference |
| `operative_from` | date | Rate start date |
| `operative_to` | date or null | Rate end date |
| `classification` | string | Which classification this applies to |

```json
[
  {
    "penalty_fixed_id": 9876,
    "description": "Sunday",
    "employee_rate_type": "ordinary",
    "rate": 200.0,
    "rate_unit": "percent",
    "calculated_value": 2.0,
    "clause": "29.2",
    "operative_from": "2023-07-01",
    "operative_to": null,
    "classification": "Retail Employee Level 2"
  }
]
```

**How to use `calculated_value`:**
```
Sunday pay = hourly_rate × calculated_value × hours_worked
           = $23.32 × 2.0 × 8 = $373.12
```

---

## Getting Allowances

### `GET /awards/{code}/allowances`

| Field | Type | Required | Notes |
|---|---|---|---|
| `date` | date | No | Point-in-time date. Omit for latest. |

```bash
GET /awards/MA000004/allowances?date=2024-03-15
```

**Response — two arrays:**

```json
{
  "expense_allowances": [ ... ],
  "wage_allowances":    [ ... ]
}
```

**Expense allowance fields** (travel, meals, tools):

| Field | Type | Description |
|---|---|---|
| `allowance` | string | Allowance name |
| `amount` | float | Dollar amount |
| `payment_frequency` | string | `"per shift"`, `"per km"`, `"per week"`, etc. |
| `is_all_purpose` | boolean | If true, included in ordinary time earnings |
| `clause` | string | Award clause reference |

**Wage allowance fields** (leading hand, etc.) — same fields plus:

| Field | Type | Description |
|---|---|---|
| `rate` | float | Percentage rate (if applicable) |
| `base_rate` | float | Base rate it applies to (if applicable) |
| `rate_unit` | string | Unit for the rate |
| `allowance_amount` | float | Fixed dollar amount |

---

## One-Shot Finder

### `GET /finder`

Gets everything — award, classification, penalties, and allowances — in a single call.
Best for when you need a full data bundle for pay calculations.

| Field | Type | Required | Notes |
|---|---|---|---|
| `award` | string | Yes | Award name search term |
| `classification` | string | Yes | Classification search term |
| `date` | date | No | Point-in-time date |
| `top` | integer | No | Alternatives to include. Default 3. |
| `include_penalties` | boolean | No | Default true |
| `include_allowances` | boolean | No | Default true |

```bash
GET /finder?award=retail&classification=level+2&date=2024-03-15
```

**Response:**

```json
{
  "resolved_at": "2024-03-15T14:30:00",
  "award": {
    "top_match":    { "award_code": "MA000004", "name": "...", "match_score": 1.0 },
    "alternatives": [ ... ]
  },
  "classification": {
    "top_match":    { "classification": "Retail Employee Level 2", "calculated_rate_hourly": 23.32, ... },
    "alternatives": [ ... ]
  },
  "penalties":          [ ... ],
  "expense_allowances": [ ... ],
  "wage_allowances":    [ ... ]
}
```

---

## Calculating Pay for a Shift

### `POST /calculate/shift`

**Request body fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `award_code` | string | Yes | e.g. `"MA000004"` |
| `classification_level` | integer | Yes | Numeric level, e.g. `2` |
| `shift` | object | Yes | Shift details (see below) |

**Shift object fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `date` | date | Yes | `YYYY-MM-DD` — used for rate lookup |
| `day_type` | string | Yes | `weekday_ordinary`, `saturday`, `sunday`, or `public_holiday` |
| `hours_worked` | float | Yes | Total hours including any overtime |
| `overtime_hours` | float | No | Hours beyond ordinary time. Default 0. |
| `allowances` | array | No | List of allowance objects (see below) |

**Allowance object fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | Descriptive name |
| `amount` | float | Yes | Dollar amount |
| `unit` | string | No | `per_shift`, `per_day`, `per_km`, `per_week`, `flat`. Default `per_shift` |
| `kilometres` | float | No | Only used when `unit` is `per_km` |

**Example — Sunday shift with meal allowance:**

```json
POST /calculate/shift

{
  "award_code": "MA000004",
  "classification_level": 2,
  "shift": {
    "date": "2024-03-10",
    "day_type": "sunday",
    "hours_worked": 9.5,
    "overtime_hours": 1.5,
    "allowances": [
      { "name": "Meal allowance", "amount": 17.03, "unit": "per_shift" }
    ]
  }
}
```

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `base_hourly_rate` | float | Rate looked up from DB for this date |
| `ordinary_hours` | float | `hours_worked` − `overtime_hours` |
| `ordinary_rate` | float | `base_rate × penalty_multiplier` |
| `ordinary_pay` | float | `ordinary_hours × ordinary_rate` |
| `penalty_applied` | string | e.g. `"200%"` for Sunday |
| `overtime_hours` | float | Hours worked as overtime |
| `overtime_pay` | float | First 2 hrs at 1.5×, remainder at 2× |
| `allowances` | array | Each allowance with its calculated subtotal |
| `allowances_total` | float | Sum of all allowances |
| `shift_gross` | float | **Total pay for this shift** |

```json
{
  "award_code": "MA000004",
  "classification_level": 2,
  "date": "2024-03-10",
  "day_type": "sunday",
  "penalty_applied": "200%",
  "base_hourly_rate": 23.32,
  "ordinary_hours": 8.0,
  "ordinary_rate": 46.64,
  "ordinary_pay": 373.12,
  "overtime_hours": 1.5,
  "overtime_pay": 52.47,
  "allowances": [
    { "name": "Meal allowance", "unit": "per_shift", "amount": 17.03, "subtotal": 17.03 }
  ],
  "allowances_total": 17.03,
  "shift_gross": 442.62
}
```

---

## Calculating a Pay Period

### `POST /calculate/period`

Same as shift but with a `shifts` array. The rate is looked up using the **first shift's date**.

**Request body fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `award_code` | string | Yes | |
| `classification_level` | integer | Yes | |
| `shifts` | array | Yes | 1–100 shift objects (same structure as above) |

```json
POST /calculate/period

{
  "award_code": "MA000004",
  "classification_level": 2,
  "shifts": [
    { "date": "2024-03-04", "day_type": "weekday_ordinary", "hours_worked": 8.0, "overtime_hours": 0.0, "allowances": [] },
    { "date": "2024-03-05", "day_type": "weekday_ordinary", "hours_worked": 8.0, "overtime_hours": 0.0, "allowances": [] },
    { "date": "2024-03-09", "day_type": "saturday",         "hours_worked": 6.0, "overtime_hours": 0.0, "allowances": [] },
    { "date": "2024-03-10", "day_type": "sunday",           "hours_worked": 8.0, "overtime_hours": 0.0, "allowances": [] }
  ]
}
```

**Response:**

```json
{
  "award_code": "MA000004",
  "classification_level": 2,
  "base_hourly_rate": 23.32,
  "rate_lookup_date": "2024-03-04",
  "shifts": [ ... ],
  "totals": {
    "total_ordinary_pay": 373.12,
    "total_overtime_pay": 0.0,
    "total_allowances":   0.0,
    "gross_pay":          746.24
  }
}
```

---

## Generating a Payslip

### `POST /payslips/generate`

Generates a complete payslip JSON using live Award rates. Compares calculated pay against
what was paid and produces an audit result automatically.

**Request body fields:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `payslip_id` | string | Yes | Your unique reference, e.g. `"PS-2024-005"` |
| `award_code` | string | Yes | |
| `employee` | object | Yes | See below |
| `pay_period` | object | Yes | See below |
| `shifts` | array | Yes | Same shift objects as `/calculate/period` |
| `paid_gross` | float | Yes | What was actually paid to the employee |
| `paid_notes` | string | No | Optional note (e.g. `"Overtime not applied"`) |

**Employee object:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `name` | string | Yes | |
| `employment_type` | string | Yes | `full_time`, `part_time`, or `casual` |
| `classification_level` | integer | Yes | |

**Pay period object:**

| Field | Type | Required | Notes |
|---|---|---|---|
| `start` | date | Yes | `YYYY-MM-DD` |
| `end` | date | Yes | `YYYY-MM-DD` |
| `type` | string | No | `weekly`, `fortnightly`, `monthly`. Default `fortnightly` |

```json
POST /payslips/generate

{
  "payslip_id": "PS-2024-005",
  "award_code": "MA000004",
  "employee": {
    "name": "Alex Brown",
    "employment_type": "full_time",
    "classification_level": 3
  },
  "pay_period": {
    "start": "2024-06-03",
    "end":   "2024-06-16",
    "type":  "fortnightly"
  },
  "shifts": [
    { "date": "2024-06-03", "day_type": "weekday_ordinary", "hours_worked": 8.0, "overtime_hours": 0.0, "allowances": [] },
    { "date": "2024-06-09", "day_type": "sunday",           "hours_worked": 8.0, "overtime_hours": 0.0, "allowances": [] }
  ],
  "paid_gross": 450.00,
  "paid_notes": "Sunday penalty not applied"
}
```

**Response — full payslip with audit:**

```json
{
  "payslip_id": "PS-2024-005",
  "generated_at": "2024-06-17T10:00:00",
  "employee": { "name": "Alex Brown", "employment_type": "full_time", "classification_level": 3 },
  "award": { "code": "MA000004", "name": "General Retail Industry Award 2020" },
  "pay_period": { "start": "2024-06-03", "end": "2024-06-16", "type": "fortnightly" },
  "base_hourly_rate": 24.20,
  "shifts": [
    {
      "date": "2024-06-03", "day_type": "weekday_ordinary",
      "ordinary_pay": 193.60, "overtime_pay": 0.0, "shift_gross": 193.60
    },
    {
      "date": "2024-06-09", "day_type": "sunday", "penalty_applied": "200%",
      "ordinary_pay": 387.20, "overtime_pay": 0.0, "shift_gross": 387.20
    }
  ],
  "calculated": {
    "total_ordinary_pay": 580.80,
    "total_overtime_pay": 0.0,
    "total_allowances":   0.0,
    "gross_pay":          580.80
  },
  "paid": {
    "gross_pay": 450.00,
    "notes": "Sunday penalty not applied"
  },
  "audit": {
    "calculated_gross": 580.80,
    "paid_gross":        450.00,
    "variance":         -130.80,
    "variance_pct":     -22.52,
    "status":           "underpaid",
    "issues":           [ "Variance of $130.80 detected — calculated $580.80, paid $450.00", "Sunday penalty not applied" ]
  }
}
```

---

## Auditing an Existing Payslip

### `POST /payslips/check`

Submit a payslip JSON (e.g. one generated by `/payslips/generate` or matching the same structure)
and receive a compliance audit result.

**Request body:** A full payslip JSON object. Minimum required fields:
- `payslip_id`
- `employee`
- `pay_period`
- `audit` (must contain `calculated_gross`, `paid_gross`, `variance`, `variance_pct`, `status`, `issues`)

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `payslip_id` | string | Payslip reference |
| `employee` | string | Employee name |
| `period` | string | `"2024-03-04 → 2024-03-17"` |
| `calculated` | float | What the employee should have been paid |
| `paid` | float | What was actually paid |
| `variance` | float | `paid − calculated` (negative = underpaid) |
| `variance_pct` | float | Variance as a percentage |
| `status` | string | `correct`, `underpaid`, or `overpaid` |
| `issues` | array | List of specific problems found |

```json
{
  "payslip_id":   "PS-2024-002",
  "employee":     "Tom Baker",
  "period":       "2024-03-04 → 2024-03-17",
  "calculated":   1234.56,
  "paid":         1032.24,
  "variance":     -202.32,
  "variance_pct": -16.39,
  "status":       "underpaid",
  "issues":       ["Sunday shifts paid at 1.0x ordinary rate instead of 2.0x"]
}
```

---

## Year-on-Year Rate Comparison

### `GET /awards/{code}/compare`

Compare classification rates between two years for an award. Useful for showing employees
how their entitlements changed after the annual wage review.

| Field | Type | Required | Notes |
|---|---|---|---|
| `year_from` | integer | Yes | Base year, e.g. `2022` |
| `year_to` | integer | Yes | Comparison year, e.g. `2024` |

```bash
GET /awards/MA000004/compare?year_from=2022&year_to=2024
```

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `award_code` | string | |
| `year_from` | integer | |
| `year_to` | integer | |
| `classifications` | array | One entry per classification level |
| `summary.total_classifications` | integer | Number of levels compared |
| `summary.avg_increase_pct` | float | Average % increase across all levels |

**Classification entry fields:**

| Field | Type | Description |
|---|---|---|
| `classification` | string | Classification name |
| `classification_level` | integer | |
| `rate_{year_from}` | float | Hourly rate in the base year |
| `rate_{year_to}` | float | Hourly rate in the comparison year |
| `increase` | float | Dollar increase |
| `increase_pct` | float | Percentage increase |

```json
{
  "award_code": "MA000004",
  "year_from": 2022,
  "year_to": 2024,
  "classifications": [
    {
      "classification": "Retail Employee Level 1",
      "classification_level": 1,
      "rate_2022": 21.38,
      "rate_2024": 23.23,
      "increase": 1.85,
      "increase_pct": 8.65
    },
    {
      "classification": "Retail Employee Level 2",
      "classification_level": 2,
      "rate_2022": 22.18,
      "rate_2024": 24.07,
      "increase": 1.89,
      "increase_pct": 8.52
    }
  ],
  "summary": {
    "total_classifications": 8,
    "avg_increase_pct": 8.72
  }
}
```

---

## Error Responses

All errors return a JSON body:

```json
{ "detail": "Description of the error." }
```

| Status | When it happens |
|---|---|
| `403` | Missing or wrong `X-API-Key` header |
| `404` | No data found for your search terms / award code / date |
| `422` | Invalid request — missing required field, wrong type, value out of range |
| `429` | Rate limit exceeded — slow down requests |
| `500` | Server error — contact the API owner |

**Common 422 causes:**
- `day_type` value not in the allowed list
- `hours_worked` is 0 or negative
- `year_to` is not greater than `year_from`
- Missing required fields in the request body

---

## Penalty Multiplier Reference

| Day type | Multiplier | Effective rate (Level 2 example @ $23.32/hr) |
|---|---|---|
| `weekday_ordinary` | 1.0× | $23.32 |
| `saturday` | 1.5× | $34.98 |
| `sunday` | 2.0× | $46.64 |
| `public_holiday` | 2.25× | $52.47 |
| Overtime (first 2 hrs) | 1.5× | $34.98 |
| Overtime (after 2 hrs) | 2.0× | $46.64 |

These are standard Modern Award values. Specific awards may have different multipliers —
always verify against the penalties from `/awards/{code}/penalties`.
