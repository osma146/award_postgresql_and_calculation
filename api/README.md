# Australian Awards API

REST API for point-in-time Award rate lookups, fuzzy search, and payslip
compliance auditing. Built with FastAPI, designed to sit behind Cloudflare.

---

## Running the API

```bash
python -m uvicorn api.main:app --reload --port 8000
```

Interactive Swagger docs are available at `http://localhost:8000/docs` while running.

---

## Authentication

Every endpoint except `/health` requires an API key in the request header:

```
X-API-Key: your-api-key-here
```

The key is set in your `.env` file as `API_KEY`.
Generate a strong key with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Any request without a valid key returns:
```json
{ "detail": "Invalid API key." }
```
HTTP status: `403 Forbidden`

---

## Base URL

| Environment | URL |
|---|---|
| Local dev | `http://localhost:8000` |
| Production | `https://api.yourdomain.com` |

---

## Endpoints

### `GET /health`

Health check — no authentication required. Use this for Cloudflare uptime monitoring.

```bash
curl https://api.yourdomain.com/health
```

**Response:**
```json
{
  "status": "ok",
  "db": "connected"
}
```

---

### `GET /awards`

Search awards by name. Handles partial matches and typos.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `search` | Yes | Award name search term (min 2 chars) |
| `top` | No | Max results to return (default 5, max 20) |

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/awards?search=retail&top=3"
```

**Response:**
```json
[
  { "award_code": "MA000004", "name": "General Retail Industry Award 2020", "match_score": 1.0 },
  { "award_code": "MA000084", "name": "Vehicle Manufacturing, Repair, Services and Retail Award 2020", "match_score": 0.36 }
]
```

Typo-tolerant — `search=retial` still returns the Retail Award.

---

### `GET /awards/{code}/classifications`

Search classifications within an award. Returns hourly and weekly rates.

**Path parameters:**

| Parameter | Description |
|---|---|
| `code` | Award code (e.g. `MA000004`) |

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `search` | Yes | Classification name or level (e.g. `level 2`) |
| `date` | No | Point-in-time date `YYYY-MM-DD` (defaults to latest) |
| `top` | No | Max results (default 5, max 20) |

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/awards/MA000004/classifications?search=level+2&date=2024-03-15"
```

**Response:**
```json
[
  {
    "classification_fixed_id": 12345,
    "classification": "Retail Employee Level 2",
    "classification_level": 2,
    "base_rate_weekly": 812.60,
    "base_rate_type": "weekly",
    "calculated_rate_hourly": 21.38,
    "calculated_rate_type": "hourly",
    "operative_from": "2023-07-01",
    "operative_to": null,
    "match_score": 0.9
  }
]
```

---

### `GET /awards/{code}/penalties`

Get penalty rates (weekends, public holidays, overtime, night shift) for an award.

**Path parameters:**

| Parameter | Description |
|---|---|
| `code` | Award code (e.g. `MA000004`) |

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `classification` | No | Filter by classification name (optional) |
| `date` | No | Point-in-time date `YYYY-MM-DD` |

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/awards/MA000004/penalties?date=2024-03-15&classification=level+2"
```

**Response:**
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

---

### `GET /awards/{code}/allowances`

Get all allowances for an award — both expense allowances (travel, meals, tools)
and wage allowances (leading hand, etc.).

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `date` | No | Point-in-time date `YYYY-MM-DD` |

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/awards/MA000004/allowances?date=2024-03-15"
```

**Response:**
```json
{
  "expense_allowances": [
    {
      "expense_allowance_fixed_id": 111,
      "allowance": "Meal allowance",
      "parent_allowance": null,
      "amount": 17.03,
      "payment_frequency": "per occasion",
      "is_all_purpose": false,
      "clause": "20.1",
      "operative_from": "2023-07-01",
      "operative_to": null
    }
  ],
  "wage_allowances": [
    {
      "wage_allowance_fixed_id": 222,
      "allowance": "Leading hand — in charge of 3 to 10 employees",
      "parent_allowance": null,
      "rate": null,
      "base_rate": null,
      "rate_unit": null,
      "allowance_amount": 43.10,
      "payment_frequency": "per week",
      "is_all_purpose": true,
      "clause": "21.3",
      "operative_from": "2023-07-01",
      "operative_to": null
    }
  ]
}
```

---

### `GET /finder`

One-shot resolver. Finds the best matching Award and Classification for your search
terms, then returns all penalties and allowances — everything you need for a pay
calculation in a single call.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `award` | Yes | Award name search term |
| `classification` | Yes | Classification search term |
| `date` | No | Point-in-time date `YYYY-MM-DD` |
| `top` | No | Number of alternative matches to include (default 3) |
| `include_penalties` | No | Include penalties in response (default true) |
| `include_allowances` | No | Include allowances in response (default true) |

**Example:**
```bash
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/finder?award=retail&classification=level+2&date=2024-03-15"
```

**Response:**
```json
{
  "resolved_at": "2024-03-15T14:30:00",
  "award": {
    "top_match": { "award_code": "MA000004", "name": "General Retail Industry Award 2020", "match_score": 1.0 },
    "alternatives": []
  },
  "classification": {
    "top_match": {
      "classification": "Retail Employee Level 2",
      "classification_level": 2,
      "calculated_rate_hourly": 21.38,
      "match_score": 0.9
    },
    "alternatives": [
      { "classification": "Retail Employee Level 1", "calculated_rate_hourly": 19.49, "match_score": 0.75 }
    ]
  },
  "penalties": [ ... ],
  "expense_allowances": [ ... ],
  "wage_allowances": [ ... ]
}
```

---

### `POST /payslips/check`

Submit a payslip JSON body and receive a compliance audit result.
The endpoint reads the `audit` block already embedded in the payslip and returns
a structured report.

**Request body:** A full payslip JSON object (same structure as the `PS-*.json` files).

**Example:**
```bash
curl -X POST \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d @payslips/PS-2024-002.json \
  "https://api.yourdomain.com/payslips/check"
```

**Response:**
```json
{
  "payslip_id": "PS-2024-002",
  "employee": "Tom Baker",
  "period": "2024-03-11 → 2024-03-17",
  "calculated": 1234.56,
  "paid": 1032.24,
  "variance": -202.32,
  "variance_pct": -16.39,
  "status": "underpaid",
  "issues": [
    "Sunday shifts paid at 1.0x ordinary rate instead of 2.0x"
  ]
}
```

**Status values:**

| Status | Meaning |
|---|---|
| `correct` | Paid matches calculated gross |
| `underpaid` | Employee was paid less than their entitlement |
| `overpaid` | Employee was paid more than their entitlement |

---

### `GET /autocomplete/awards`

Live award name search — call on every keystroke. Returns top 10 closest matches
ranked by how well they match what the user has typed so far.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `q` | Yes | Partial award name (1+ characters) |
| `top` | No | Max results (default 10, max 20) |

**Behaviour by query length:**
- **1–2 chars** — prefix match only (`retail` starts with `re`) — fast, low noise
- **3+ chars** — prefix match + fuzzy combined, ranked by closeness score

**Example — wire this to your input's `onChange`:**
```bash
# User typed "r"
curl -H "X-API-Key: your-key" "https://api.yourdomain.com/autocomplete/awards?q=r"

# User typed "re"
curl -H "X-API-Key: your-key" "https://api.yourdomain.com/autocomplete/awards?q=re"

# User typed "ret" (fuzzy kicks in — typo "reta" also works)
curl -H "X-API-Key: your-key" "https://api.yourdomain.com/autocomplete/awards?q=ret"
```

**Response:**
```json
[
  { "award_code": "MA000004", "name": "General Retail Industry Award 2020",     "score": 0.9 },
  { "award_code": "MA000084", "name": "Vehicle ... Retail Award 2020",          "score": 0.45 },
  { "award_code": "MA000059", "name": "Retail Award 2010",                      "score": 0.36 }
]
```

---

### `GET /autocomplete/classifications`

Live classification search within a chosen award. Typically used in step 2 after
the user has selected an award from the autocomplete dropdown.

**Query parameters:**

| Parameter | Required | Description |
|---|---|---|
| `award` | Yes | Award code from step 1 (e.g. `MA000004`) |
| `q` | Yes | Partial classification name or level (1+ characters) |
| `top` | No | Max results (default 10, max 20) |

**Example:**
```bash
# User selected MA000004, now typing "lev"
curl -H "X-API-Key: your-key" \
  "https://api.yourdomain.com/autocomplete/classifications?award=MA000004&q=lev"
```

**Response:**
```json
[
  { "classification_fixed_id": 12341, "classification": "Retail Employee Level 1", "classification_level": 1, "calculated_rate_hourly": 19.49 },
  { "classification_fixed_id": 12342, "classification": "Retail Employee Level 2", "classification_level": 2, "calculated_rate_hourly": 21.38 },
  { "classification_fixed_id": 12343, "classification": "Retail Employee Level 3", "classification_level": 3, "calculated_rate_hourly": 22.18 }
]
```

**Typical frontend flow:**
```
User types in award box  →  GET /autocomplete/awards?q={input}     →  show dropdown
User selects an award    →  store award_code
User types in class box  →  GET /autocomplete/classifications
                              ?award={award_code}&q={input}         →  show dropdown
User selects a class     →  you now have hourly rate + level
```

---

## Rate Limits

| Endpoint group | Limit |
|---|---|
| `/awards/*`, `/health` | 60 requests per minute per IP |
| `/finder`, `/payslips/check` | 30 requests per minute per IP |
| `/autocomplete/*` | 120 requests per minute per IP |

Rate limits are applied per real IP address. When behind Cloudflare, the
`CF-Connecting-IP` header is used as the real client IP.

Exceeding the limit returns HTTP `429 Too Many Requests`.

---

## Error Responses

| Status | Meaning |
|---|---|
| `403` | Invalid or missing `X-API-Key` |
| `404` | No results found for search term |
| `422` | Invalid or missing request parameters |
| `429` | Rate limit exceeded |
| `500` | Server or database error |

All errors return a JSON body:
```json
{ "detail": "Description of the error." }
```

---

## CORS

The API only accepts requests from origins listed in `ALLOWED_ORIGINS` in `.env`.
Add your frontend domain there — no trailing slashes:

```ini
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

During local development you can add `http://localhost:3000` to the list.

---

## Cloudflare Setup

1. Point your domain's DNS A record to your server IP via Cloudflare (proxy enabled — orange cloud)
2. Cloudflare handles HTTPS automatically
3. In Cloudflare, set up a health check monitor pointing to `https://api.yourdomain.com/health`
4. The API uses `CF-Connecting-IP` for accurate per-IP rate limiting automatically
