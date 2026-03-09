# React Integration Guide

How to connect a React frontend to the Awards API. Covers project setup,
environment variables, a reusable API client, and ready-to-use hooks and
components for every major feature.

---

## Project Setup

### Install dependencies

```bash
npm create vite@latest my-awards-app -- --template react
cd my-awards-app
npm install axios
```

### Environment variables

Create `.env` in your React project root:

```ini
VITE_API_BASE_URL=https://api.yourdomain.com
VITE_API_KEY=your-api-key-here
```

> Never commit this file. Add `.env` to `.gitignore`.

---

## API Client

Create `src/api/client.js` — a single axios instance used by all hooks:

```javascript
// src/api/client.js
import axios from 'axios';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  headers: {
    'X-API-Key': import.meta.env.VITE_API_KEY,
    'Content-Type': 'application/json',
  },
});

export default client;
```

---

## Custom Hooks

### `useAwardSearch` — search awards by name

```javascript
// src/hooks/useAwardSearch.js
import { useState, useCallback } from 'react';
import client from '../api/client';

export function useAwardSearch() {
  const [results, setResults]   = useState([]);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState(null);

  const search = useCallback(async (term, top = 5) => {
    if (!term || term.length < 2) { setResults([]); return; }
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.get('/awards', { params: { search: term, top } });
      setResults(data);
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  return { results, loading, error, search };
}
```

### `useAutocomplete` — live per-keystroke search with debounce

```javascript
// src/hooks/useAutocomplete.js
import { useState, useEffect, useRef } from 'react';
import client from '../api/client';

export function useAwardAutocomplete(query, top = 10) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (!query) { setResults([]); return; }

    // Debounce — wait 250ms after user stops typing
    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await client.get('/autocomplete/awards', {
          params: { q: query, top },
        });
        setResults(data);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer.current);
  }, [query, top]);

  return { results, loading };
}

export function useClassificationAutocomplete(awardCode, query, top = 10) {
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const timer = useRef(null);

  useEffect(() => {
    if (!awardCode || !query) { setResults([]); return; }

    clearTimeout(timer.current);
    timer.current = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await client.get('/autocomplete/classifications', {
          params: { award: awardCode, q: query, top },
        });
        setResults(data);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => clearTimeout(timer.current);
  }, [awardCode, query, top]);

  return { results, loading };
}
```

### `useShiftCalculator` — calculate pay for a shift

```javascript
// src/hooks/useShiftCalculator.js
import { useState, useCallback } from 'react';
import client from '../api/client';

export function useShiftCalculator() {
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const calculate = useCallback(async ({ awardCode, classificationLevel, shift }) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.post('/calculate/shift', {
        award_code:            awardCode,
        classification_level:  classificationLevel,
        shift,
      });
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Calculation failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  return { result, loading, error, calculate };
}
```

### `usePeriodCalculator` — calculate a full pay period

```javascript
// src/hooks/usePeriodCalculator.js
import { useState, useCallback } from 'react';
import client from '../api/client';

export function usePeriodCalculator() {
  const [result, setResult]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const calculate = useCallback(async ({ awardCode, classificationLevel, shifts }) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.post('/calculate/period', {
        award_code:           awardCode,
        classification_level: classificationLevel,
        shifts,
      });
      setResult(data);
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Calculation failed');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, []);

  return { result, loading, error, calculate };
}
```

### `usePayslip` — generate and check payslips

```javascript
// src/hooks/usePayslip.js
import { useState, useCallback } from 'react';
import client from '../api/client';

export function usePayslipGenerator() {
  const [payslip, setPayslip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const generate = useCallback(async (request) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.post('/payslips/generate', request);
      setPayslip(data);
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Generation failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return { payslip, loading, error, generate };
}

export function usePayslipChecker() {
  const [audit, setAudit]   = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const check = useCallback(async (payslipJson) => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await client.post('/payslips/check', payslipJson);
      setAudit(data);
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Check failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return { audit, loading, error, check };
}
```

### `useRateComparison` — year-on-year comparison

```javascript
// src/hooks/useRateComparison.js
import { useState, useCallback } from 'react';
import client from '../api/client';

export function useRateComparison() {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const compare = useCallback(async (awardCode, yearFrom, yearTo) => {
    setLoading(true);
    setError(null);
    try {
      const { data: result } = await client.get(
        `/awards/${awardCode}/compare`,
        { params: { year_from: yearFrom, year_to: yearTo } }
      );
      setData(result);
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Comparison failed');
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, compare };
}
```

---

## Components

### Award + Classification Search Bar (two-step autocomplete)

```jsx
// src/components/AwardSelector.jsx
import { useState } from 'react';
import { useAwardAutocomplete, useClassificationAutocomplete } from '../hooks/useAutocomplete';

export default function AwardSelector({ onSelect }) {
  const [awardInput, setAwardInput]   = useState('');
  const [classInput, setClassInput]   = useState('');
  const [selectedAward, setSelectedAward] = useState(null);

  const { results: awardResults, loading: awardLoading } =
    useAwardAutocomplete(awardInput);

  const { results: classResults, loading: classLoading } =
    useClassificationAutocomplete(selectedAward?.award_code, classInput);

  const handleAwardSelect = (award) => {
    setSelectedAward(award);
    setAwardInput(award.name);
    setClassInput('');
  };

  const handleClassSelect = (cls) => {
    onSelect({ award: selectedAward, classification: cls });
    setClassInput(cls.classification);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Step 1: Award search */}
      <div>
        <label>Award</label>
        <input
          value={awardInput}
          onChange={e => { setAwardInput(e.target.value); setSelectedAward(null); }}
          placeholder="Type award name..."
        />
        {awardLoading && <span> Searching...</span>}
        {!selectedAward && awardResults.length > 0 && (
          <ul style={{ border: '1px solid #ccc', listStyle: 'none', padding: 0, margin: 0 }}>
            {awardResults.map(a => (
              <li
                key={a.award_code}
                onClick={() => handleAwardSelect(a)}
                style={{ padding: 8, cursor: 'pointer' }}
              >
                {a.name}
                <small style={{ color: '#888', marginLeft: 8 }}>({a.award_code})</small>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Step 2: Classification search — only shown after award is selected */}
      {selectedAward && (
        <div>
          <label>Classification</label>
          <input
            value={classInput}
            onChange={e => setClassInput(e.target.value)}
            placeholder="Type level or name..."
          />
          {classLoading && <span> Searching...</span>}
          {classResults.length > 0 && (
            <ul style={{ border: '1px solid #ccc', listStyle: 'none', padding: 0, margin: 0 }}>
              {classResults.map(c => (
                <li
                  key={c.classification_fixed_id}
                  onClick={() => handleClassSelect(c)}
                  style={{ padding: 8, cursor: 'pointer' }}
                >
                  {c.classification}
                  <small style={{ color: '#888', marginLeft: 8 }}>
                    ${c.calculated_rate_hourly}/hr
                  </small>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

    </div>
  );
}
```

### Shift Pay Calculator

```jsx
// src/components/ShiftCalculator.jsx
import { useState } from 'react';
import { useShiftCalculator } from '../hooks/useShiftCalculator';

const DAY_TYPES = ['weekday_ordinary', 'saturday', 'sunday', 'public_holiday'];

export default function ShiftCalculator({ awardCode, classificationLevel }) {
  const [date, setDate]           = useState('');
  const [dayType, setDayType]     = useState('weekday_ordinary');
  const [hours, setHours]         = useState(8);
  const [overtime, setOvertime]   = useState(0);
  const { result, loading, error, calculate } = useShiftCalculator();

  const handleSubmit = (e) => {
    e.preventDefault();
    calculate({
      awardCode,
      classificationLevel,
      shift: {
        date,
        day_type:       dayType,
        hours_worked:   parseFloat(hours),
        overtime_hours: parseFloat(overtime),
        allowances:     [],
      },
    });
  };

  return (
    <div>
      <h3>Shift Pay Calculator</h3>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <input type="date" value={date} onChange={e => setDate(e.target.value)} required />
        <select value={dayType} onChange={e => setDayType(e.target.value)}>
          {DAY_TYPES.map(d => <option key={d} value={d}>{d.replace(/_/g, ' ')}</option>)}
        </select>
        <input type="number" value={hours}    onChange={e => setHours(e.target.value)}
               placeholder="Hours worked" step="0.5" min="0.5" max="24" />
        <input type="number" value={overtime} onChange={e => setOvertime(e.target.value)}
               placeholder="Overtime hours" step="0.5" min="0" />
        <button type="submit" disabled={loading || !date}>
          {loading ? 'Calculating...' : 'Calculate'}
        </button>
      </form>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {result && (
        <div style={{ marginTop: 16, padding: 12, background: '#f5f5f5', borderRadius: 4 }}>
          <p><strong>Base rate:</strong> ${result.base_hourly_rate}/hr</p>
          <p><strong>Penalty applied:</strong> {result.penalty_applied}</p>
          <p><strong>Ordinary pay:</strong> ${result.ordinary_pay.toFixed(2)}</p>
          <p><strong>Overtime pay:</strong> ${result.overtime_pay.toFixed(2)}</p>
          <p><strong>Allowances:</strong> ${result.allowances_total.toFixed(2)}</p>
          <hr />
          <p style={{ fontSize: '1.2em' }}>
            <strong>Gross pay: ${result.shift_gross.toFixed(2)}</strong>
          </p>
        </div>
      )}
    </div>
  );
}
```

### Payslip Audit Display

```jsx
// src/components/PayslipAudit.jsx
const STATUS_COLOUR = {
  correct:   '#22c55e',
  underpaid: '#ef4444',
  overpaid:  '#f59e0b',
};

export default function PayslipAudit({ audit }) {
  if (!audit) return null;
  const { status, calculated_gross, paid_gross, variance, variance_pct, issues } = audit;
  const sign = variance > 0 ? '+' : '';

  return (
    <div style={{
      border: `2px solid ${STATUS_COLOUR[status]}`,
      borderRadius: 6,
      padding: 16,
      marginTop: 16,
    }}>
      <h3 style={{ color: STATUS_COLOUR[status], margin: 0 }}>
        {status.toUpperCase()}
      </h3>
      <table style={{ marginTop: 12, width: '100%' }}>
        <tbody>
          <tr><td>Calculated (correct)</td><td>${calculated_gross.toFixed(2)}</td></tr>
          <tr><td>Actually paid</td>        <td>${paid_gross.toFixed(2)}</td></tr>
          <tr>
            <td><strong>Variance</strong></td>
            <td style={{ color: STATUS_COLOUR[status] }}>
              <strong>{sign}${Math.abs(variance).toFixed(2)} ({sign}{variance_pct.toFixed(2)}%)</strong>
            </td>
          </tr>
        </tbody>
      </table>
      {issues.length > 0 && (
        <ul style={{ marginTop: 12, color: '#ef4444' }}>
          {issues.map((issue, i) => <li key={i}>{issue}</li>)}
        </ul>
      )}
    </div>
  );
}
```

### Rate Comparison Table

```jsx
// src/components/RateComparison.jsx
import { useState } from 'react';
import { useRateComparison } from '../hooks/useRateComparison';

export default function RateComparison({ awardCode }) {
  const [yearFrom, setYearFrom] = useState(2022);
  const [yearTo, setYearTo]     = useState(2024);
  const { data, loading, error, compare } = useRateComparison();

  return (
    <div>
      <h3>Rate Comparison</h3>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
        <input type="number" value={yearFrom} onChange={e => setYearFrom(+e.target.value)}
               min="2015" max="2099" style={{ width: 80 }} />
        <span>vs</span>
        <input type="number" value={yearTo} onChange={e => setYearTo(+e.target.value)}
               min="2015" max="2099" style={{ width: 80 }} />
        <button onClick={() => compare(awardCode, yearFrom, yearTo)} disabled={loading}>
          {loading ? 'Loading...' : 'Compare'}
        </button>
      </div>

      {error && <p style={{ color: 'red' }}>{error}</p>}

      {data && (
        <>
          <p style={{ color: '#888' }}>
            Average increase: {data.summary.avg_increase_pct}% across {data.summary.total_classifications} levels
          </p>
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: 8 }}>
            <thead>
              <tr style={{ background: '#f3f4f6' }}>
                <th style={{ textAlign: 'left', padding: '6px 8px' }}>Classification</th>
                <th style={{ padding: '6px 8px' }}>{yearFrom}</th>
                <th style={{ padding: '6px 8px' }}>{yearTo}</th>
                <th style={{ padding: '6px 8px' }}>Increase</th>
                <th style={{ padding: '6px 8px' }}>%</th>
              </tr>
            </thead>
            <tbody>
              {data.classifications.map(c => (
                <tr key={c.classification_level} style={{ borderBottom: '1px solid #e5e7eb' }}>
                  <td style={{ padding: '6px 8px' }}>{c.classification}</td>
                  <td style={{ textAlign: 'right', padding: '6px 8px' }}>
                    ${c[`rate_${yearFrom}`].toFixed(2)}
                  </td>
                  <td style={{ textAlign: 'right', padding: '6px 8px' }}>
                    ${c[`rate_${yearTo}`].toFixed(2)}
                  </td>
                  <td style={{ textAlign: 'right', padding: '6px 8px', color: '#22c55e' }}>
                    +${c.increase.toFixed(2)}
                  </td>
                  <td style={{ textAlign: 'right', padding: '6px 8px', color: '#22c55e' }}>
                    +{c.increase_pct.toFixed(2)}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}
```

---

## Putting It Together — Example App

```jsx
// src/App.jsx
import { useState } from 'react';
import AwardSelector    from './components/AwardSelector';
import ShiftCalculator  from './components/ShiftCalculator';
import RateComparison   from './components/RateComparison';

export default function App() {
  const [selection, setSelection] = useState(null);

  return (
    <div style={{ maxWidth: 720, margin: '0 auto', padding: 24 }}>
      <h1>Australian Awards Pay Calculator</h1>

      {/* Step 1: Select award and classification */}
      <section style={{ marginBottom: 32 }}>
        <h2>1. Find Award & Classification</h2>
        <AwardSelector onSelect={setSelection} />
        {selection && (
          <p style={{ marginTop: 8, color: '#22c55e' }}>
            ✓ {selection.award.name} — {selection.classification.classification} (${selection.classification.calculated_rate_hourly}/hr)
          </p>
        )}
      </section>

      {/* Step 2: Calculate a shift */}
      {selection && (
        <section style={{ marginBottom: 32 }}>
          <h2>2. Calculate Shift Pay</h2>
          <ShiftCalculator
            awardCode={selection.award.award_code}
            classificationLevel={selection.classification.classification_level}
          />
        </section>
      )}

      {/* Step 3: Year comparison */}
      {selection && (
        <section>
          <h2>3. Compare Rates Across Years</h2>
          <RateComparison awardCode={selection.award.award_code} />
        </section>
      )}
    </div>
  );
}
```

---

## Recommended File Structure

```
src/
├── api/
│   └── client.js               ← axios instance with base URL + API key
├── hooks/
│   ├── useAutocomplete.js      ← award + classification live search
│   ├── useShiftCalculator.js   ← single shift calculation
│   ├── usePeriodCalculator.js  ← pay period calculation
│   ├── usePayslip.js           ← generate + check payslips
│   └── useRateComparison.js    ← year-on-year comparison
├── components/
│   ├── AwardSelector.jsx       ← two-step autocomplete search bar
│   ├── ShiftCalculator.jsx     ← shift pay form + result
│   ├── PayslipAudit.jsx        ← audit result display
│   └── RateComparison.jsx      ← year-on-year comparison table
└── App.jsx
```

---

## Error Handling Pattern

All hooks return an `error` string when a request fails. Show it to the user:

```jsx
{error && (
  <div style={{ color: 'red', padding: 8, background: '#fef2f2', borderRadius: 4 }}>
    {error}
  </div>
)}
```

Common errors and what they mean:
| Error | Cause |
|---|---|
| `"No matches found."` | Search term returned nothing — try a different word |
| `"No rate found for award..."` | Award code or level doesn't exist for that date |
| `"Invalid API key."` | Wrong key in `.env` |
| `"year_to must be greater than year_from"` | Fix the year inputs |
