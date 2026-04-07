CREATE TABLE IF NOT EXISTS articles (
    guid              TEXT PRIMARY KEY,
    topic             TEXT NOT NULL,
    title             TEXT NOT NULL,
    url               TEXT NOT NULL,
    published_at      TIMESTAMPTZ,
    content           TEXT NOT NULL,
    feed_url          TEXT NOT NULL,
    symbol            TEXT,
    pct_change_day    DOUBLE PRECISION,
    last_price        DOUBLE PRECISION,
    previous_close    DOUBLE PRECISION,
    currency          TEXT,
    first_seen_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS articles_topic_published_idx
    ON articles (topic, published_at DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS articles_symbol_idx
    ON articles (symbol)
    WHERE symbol IS NOT NULL;

CREATE TABLE IF NOT EXISTS digest_summaries (
    id              BIGSERIAL PRIMARY KEY,
    run_at          TIMESTAMPTZ NOT NULL,
    scope           TEXT NOT NULL,
    topic           TEXT NOT NULL,
    symbol          TEXT,
    bullets         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_at, scope)
);

CREATE INDEX IF NOT EXISTS digest_summaries_run_at_idx
    ON digest_summaries (run_at DESC);

CREATE INDEX IF NOT EXISTS digest_summaries_topic_idx
    ON digest_summaries (topic);

CREATE TABLE IF NOT EXISTS digest_summary_sources (
    digest_summary_id   BIGINT NOT NULL REFERENCES digest_summaries(id) ON DELETE CASCADE,
    article_guid        TEXT NOT NULL REFERENCES articles(guid) ON DELETE CASCADE,
    PRIMARY KEY (digest_summary_id, article_guid)
);

CREATE INDEX IF NOT EXISTS digest_summary_sources_article_guid_idx
    ON digest_summary_sources (article_guid);
