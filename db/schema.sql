-- GOAT Life GTM system — Sprint 1 data layer schema.
-- One dimension table (localities) + append-only fact tables (locality_scores,
-- shelf_snapshots) so historical queries work without ever overwriting data.

CREATE TABLE IF NOT EXISTS localities (
    locality_id     SERIAL PRIMARY KEY,
    loc_key         TEXT UNIQUE NOT NULL,
    area            TEXT NOT NULL,
    city            TEXT NOT NULL,
    pincode         TEXT,
    lat             DOUBLE PRECISION,
    lng             DOUBLE PRECISION,
    belt_id         TEXT,
    belt_size       INTEGER,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    pipeline_run_id          SERIAL PRIMARY KEY,
    triggered_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_parquet_filename    TEXT NOT NULL,
    row_count                   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS locality_scores (
    locality_score_id           SERIAL PRIMARY KEY,
    locality_id                  INTEGER NOT NULL REFERENCES localities(locality_id),
    pipeline_run_id               INTEGER NOT NULL REFERENCES pipeline_runs(pipeline_run_id),
    as_of                          TIMESTAMPTZ NOT NULL DEFAULT now(),
    icp_score                       DOUBLE PRECISION,
    icp_verdict                      TEXT,
    gtm_action                        TEXT,
    serviceability_state               TEXT,
    serviceability_confidence           TEXT,
    archetype_ml                         TEXT,
    lifecycle                             TEXT,
    n_brands_confirmed                     INTEGER,
    brands_confirmed_list                   TEXT,
    nearest_known_darkstore_km               DOUBLE PRECISION,
    blinkit_confirmed                         BOOLEAN,
    swiggy_confirmed                           BOOLEAN,
    zepto_confirmed                             BOOLEAN,
    res_avg_buy_imputed                          DOUBLE PRECISION,
    price_is_imputed                              BOOLEAN,
    employer_quality                               TEXT,
    primary_sector                                  TEXT,
    is_metro_connected                               BOOLEAN,
    pareto_optimal                                    BOOLEAN,
    hidden_gem_v2                                      BOOLEAN,
    spillover_gem                                       BOOLEAN
);
CREATE INDEX IF NOT EXISTS idx_locality_scores_locality_id ON locality_scores(locality_id);
CREATE INDEX IF NOT EXISTS idx_locality_scores_as_of ON locality_scores(as_of);

CREATE OR REPLACE VIEW current_locality_scores AS
SELECT DISTINCT ON (locality_id) *
FROM locality_scores
ORDER BY locality_id, as_of DESC;

CREATE TABLE IF NOT EXISTS scrape_runs (
    scrape_run_id   SERIAL PRIMARY KEY,
    platform         TEXT NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    row_count            INTEGER NOT NULL DEFAULT 0,
    source_file           TEXT NOT NULL
);
-- Sprint 6 (completeness gate): a run's trust status. 'valid' runs feed the
-- week-over-week comparison; 'quarantined' runs are kept for audit but never
-- selected as the newest/second-newest run (see fetch_latest_two_scrape_run_ids).
-- Reversible by design — quarantining is an UPDATE, never a DELETE, so a run
-- wrongly flagged can be restored. Added via ALTER for tables that predate it.
ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'valid';
ALTER TABLE scrape_runs ADD COLUMN IF NOT EXISTS quarantine_reason TEXT;

CREATE TABLE IF NOT EXISTS shelf_snapshots (
    shelf_snapshot_id  SERIAL PRIMARY KEY,
    scrape_run_id        INTEGER NOT NULL REFERENCES scrape_runs(scrape_run_id),
    platform               TEXT NOT NULL,
    locality_id              INTEGER REFERENCES localities(locality_id),
    city_raw                  TEXT NOT NULL,
    locality_raw                TEXT NOT NULL,
    brand_searched                TEXT,
    rank                            INTEGER,
    product_name                     TEXT,
    pack_size                          TEXT,
    selling_price                        NUMERIC,
    mrp                                    NUMERIC,
    discount_pct                             NUMERIC,
    stock_left                                 TEXT,
    rating                                       TEXT,
    reviews                                        TEXT,
    sponsored                                       BOOLEAN,
    serviceable                                       TEXT,
    is_goat                                             BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE INDEX IF NOT EXISTS idx_shelf_snapshots_locality_id ON shelf_snapshots(locality_id);
CREATE INDEX IF NOT EXISTS idx_shelf_snapshots_platform ON shelf_snapshots(platform);
CREATE INDEX IF NOT EXISTS idx_shelf_snapshots_scrape_run_id ON shelf_snapshots(scrape_run_id);

CREATE TABLE IF NOT EXISTS locality_annotations (
    annotation_id    SERIAL PRIMARY KEY,
    locality_id        INTEGER NOT NULL REFERENCES localities(locality_id),
    note                 TEXT,
    status                 TEXT,
    budget_note              NUMERIC,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_locality_annotations_locality_id ON locality_annotations(locality_id);

-- Sprint 4: replaces the antigravity repo's drop_calendar.json file. A SKU
-- in this table is suppressed from goat_displaced/gone_products alerts —
-- GOAT Life runs intentional limited "drops" (streetwear-style scarcity),
-- so a SKU going out of stock is often deliberate, not a real disruption.
CREATE TABLE IF NOT EXISTS sku_drop_calendar (
    drop_calendar_id  SERIAL PRIMARY KEY,
    sku_name          TEXT UNIQUE NOT NULL,
    paused_since      TIMESTAMPTZ NOT NULL DEFAULT now(),
    note              TEXT
);
