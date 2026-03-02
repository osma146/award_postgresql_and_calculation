-- ============================================================
-- Australian Modern Awards - Database Schema
-- ============================================================
-- Run this once to create all tables before importing Excel data.
-- All tables include operative_from / operative_to for historical
-- point-in-time lookups (e.g. "what was the rate on 2019-03-15?")
-- ============================================================

-- pg_trgm: enables fuzzy/typo-tolerant text search
-- e.g. "retial" still finds "retail", "penlty" still finds "penalty"
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Awards master list
CREATE TABLE IF NOT EXISTS awards (
    award_fixed_id      INTEGER         NOT NULL,
    award_code          VARCHAR(20)     NOT NULL,
    name                TEXT            NOT NULL,
    operative_from      DATE,
    operative_to        DATE,
    published_year      INTEGER         NOT NULL,
    PRIMARY KEY (award_fixed_id, published_year)
);

-- Classifications (Factor 1 + 2: class level + base wage rate)
CREATE TABLE IF NOT EXISTS classifications (
    id                          SERIAL          PRIMARY KEY,
    award_code                  VARCHAR(20)     NOT NULL,
    classification_fixed_id     INTEGER         NOT NULL,
    published_year              INTEGER         NOT NULL,
    classification              TEXT,
    classification_level        INTEGER,
    parent_classification_name  TEXT,
    clause                      TEXT,
    base_rate                   NUMERIC(12,4),  -- weekly rate
    base_rate_type              VARCHAR(20),
    calculated_rate             NUMERIC(12,4),  -- hourly rate
    calculated_rate_type        VARCHAR(20),
    calculated_includes_all_purpose BOOLEAN,
    operative_from              DATE,
    operative_to                DATE,
    UNIQUE (classification_fixed_id, published_year)
);

-- Penalty rates (Factor 3)
CREATE TABLE IF NOT EXISTS penalties (
    id                          SERIAL          PRIMARY KEY,
    award_code                  VARCHAR(20)     NOT NULL,
    penalty_fixed_id            INTEGER         NOT NULL,
    published_year              INTEGER         NOT NULL,
    classification              TEXT,
    classification_level        INTEGER,
    parent_classification_name  TEXT,
    clause                      TEXT,
    penalty_description         TEXT,
    employee_rate_type_code     VARCHAR(20),
    rate                        NUMERIC(12,4),  -- e.g. 150 = 150%
    penalty_rate_unit           VARCHAR(50),    -- "Percent" or "Dollar"
    penalty_calculated_value    NUMERIC(12,4),  -- actual $ value
    calculated_includes_all_purpose BOOLEAN,
    operative_from              DATE,
    operative_to                DATE,
    UNIQUE (penalty_fixed_id, published_year)
);

-- Expense allowances (Factor 4a)
CREATE TABLE IF NOT EXISTS expense_allowances (
    id                              SERIAL          PRIMARY KEY,
    award_code                      VARCHAR(20)     NOT NULL,
    expense_allowance_fixed_id      INTEGER         NOT NULL,
    published_year                  INTEGER         NOT NULL,
    allowance                       TEXT,
    parent_allowance                TEXT,
    clause                          VARCHAR(50),
    allowance_amount                NUMERIC(12,4),
    payment_frequency               VARCHAR(100),
    is_all_purpose                  BOOLEAN,
    operative_from                  DATE,
    operative_to                    DATE,
    UNIQUE (expense_allowance_fixed_id, published_year)
);

-- Wage allowances (Factor 4b)
CREATE TABLE IF NOT EXISTS wage_allowances (
    id                          SERIAL          PRIMARY KEY,
    award_code                  VARCHAR(20)     NOT NULL,
    wage_allowance_fixed_id     INTEGER         NOT NULL,
    published_year              INTEGER         NOT NULL,
    allowance                   TEXT,
    parent_allowance            TEXT,
    clause                      TEXT,
    rate                        NUMERIC(12,4),  -- % of base rate
    base_rate                   NUMERIC(12,4),
    rate_unit                   VARCHAR(50),
    allowance_amount            NUMERIC(12,4),
    payment_frequency           VARCHAR(100),
    is_all_purpose              BOOLEAN,
    operative_from              DATE,
    operative_to                DATE,
    UNIQUE (wage_allowance_fixed_id, published_year)
);

-- ============================================================
-- Indexes for fast point-in-time lookups
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_classifications_award    ON classifications (award_code);
CREATE INDEX IF NOT EXISTS idx_classifications_dates    ON classifications (operative_from, operative_to);
CREATE INDEX IF NOT EXISTS idx_classifications_year     ON classifications (published_year);

CREATE INDEX IF NOT EXISTS idx_penalties_award          ON penalties (award_code);
CREATE INDEX IF NOT EXISTS idx_penalties_dates          ON penalties (operative_from, operative_to);
CREATE INDEX IF NOT EXISTS idx_penalties_year           ON penalties (published_year);

CREATE INDEX IF NOT EXISTS idx_expense_allow_award      ON expense_allowances (award_code);
CREATE INDEX IF NOT EXISTS idx_expense_allow_dates      ON expense_allowances (operative_from, operative_to);

CREATE INDEX IF NOT EXISTS idx_wage_allow_award         ON wage_allowances (award_code);
CREATE INDEX IF NOT EXISTS idx_wage_allow_dates         ON wage_allowances (operative_from, operative_to);

-- ============================================================
-- Full-text search indexes
-- Enables fast name/keyword search across awards and classifications
-- Uses GIN index on tsvector — handles partial words and ranking
-- ============================================================

-- Search awards by name (e.g. "retail", "hospitality", "mining")
CREATE INDEX IF NOT EXISTS idx_awards_name_fts
    ON awards USING GIN (to_tsvector('english', name));

-- Search classifications by name (e.g. "leading hand", "level 3", "cook")
CREATE INDEX IF NOT EXISTS idx_classifications_name_fts
    ON classifications USING GIN (to_tsvector('english', COALESCE(classification, '')));

-- Search penalties by description (e.g. "sunday", "overtime", "night shift")
CREATE INDEX IF NOT EXISTS idx_penalties_desc_fts
    ON penalties USING GIN (to_tsvector('english', COALESCE(penalty_description, '')));

-- Search allowances by name (e.g. "travel", "meal", "tool")
CREATE INDEX IF NOT EXISTS idx_expense_allow_name_fts
    ON expense_allowances USING GIN (to_tsvector('english', COALESCE(allowance, '')));

CREATE INDEX IF NOT EXISTS idx_wage_allow_name_fts
    ON wage_allowances USING GIN (to_tsvector('english', COALESCE(allowance, '')));

-- ============================================================
-- Trigram indexes for fuzzy / typo-tolerant search (pg_trgm)
-- Handles misspellings: "retial" still finds "retail"
-- Used with: WHERE name % 'retial' OR similarity(name, 'retial') > 0.3
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_awards_name_trgm
    ON awards USING GIN (name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_classifications_trgm
    ON classifications USING GIN (COALESCE(classification, '') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_penalties_trgm
    ON penalties USING GIN (COALESCE(penalty_description, '') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_expense_allow_trgm
    ON expense_allowances USING GIN (COALESCE(allowance, '') gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_wage_allow_trgm
    ON wage_allowances USING GIN (COALESCE(allowance, '') gin_trgm_ops);

-- ============================================================
-- Example search queries (for reference — do not run as part of setup)
-- ============================================================

-- Search awards by keyword:
--   SELECT award_code, name
--   FROM awards
--   WHERE to_tsvector('english', name) @@ to_tsquery('english', 'retail')
--   GROUP BY award_code, name ORDER BY name;

-- Search awards with partial/fuzzy name (ILIKE — simpler, slightly slower):
--   SELECT award_code, name FROM awards
--   WHERE name ILIKE '%retail%'
--   GROUP BY award_code, name ORDER BY name;

-- Find all classifications matching a keyword for a specific award + year:
--   SELECT classification, classification_level, calculated_rate
--   FROM classifications
--   WHERE award_code = 'MA000004'
--     AND published_year = 2024
--     AND to_tsvector('english', COALESCE(classification, ''))
--         @@ to_tsquery('english', 'leading & hand');

-- Point-in-time rate lookup (what was the rate on a specific date?):
--   SELECT classification, calculated_rate, operative_from, operative_to
--   FROM classifications
--   WHERE award_code = 'MA000004'
--     AND operative_from <= '2022-03-15'
--     AND (operative_to >= '2022-03-15' OR operative_to IS NULL)
--   ORDER BY classification_level;

-- Fuzzy/typo-tolerant search on award name (handles misspellings):
-- word_similarity checks if the search term matches any single word in the text,
-- which works well for short typos inside a longer award name.
--   SELECT award_code, name, ROUND(word_similarity('retial', name)::numeric, 2) AS score
--   FROM awards
--   WHERE word_similarity('retial', name) > 0.4
--   GROUP BY award_code, name ORDER BY score DESC;

-- Compare rates across two years for the same award:
--   SELECT
--       a.classification,
--       a.calculated_rate  AS rate_2022,
--       b.calculated_rate  AS rate_2024,
--       ROUND(b.calculated_rate - a.calculated_rate, 4) AS increase
--   FROM classifications a
--   JOIN classifications b
--     ON a.classification_fixed_id = b.classification_fixed_id
--   WHERE a.published_year = 2022
--     AND b.published_year = 2024
--     AND a.award_code = 'MA000004'
--   ORDER BY a.classification_level;
