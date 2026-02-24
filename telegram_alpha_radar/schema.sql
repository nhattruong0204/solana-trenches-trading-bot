-- ============================================================
-- Telegram Alpha Radar — PostgreSQL Schema
-- ============================================================
-- Run once to initialize:
--   psql -U radar -d alpha_radar -f schema.sql
-- ============================================================

-- Main mentions table
CREATE TABLE IF NOT EXISTS contract_mentions (
    id              BIGSERIAL       PRIMARY KEY,
    contract        TEXT            NOT NULL,
    chain           TEXT            NOT NULL,
    chat_id         BIGINT          NOT NULL,
    message_id      BIGINT          NOT NULL,
    mentioned_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Deduplication: same contract + same chat + same message = 1 row
    UNIQUE (contract, chat_id, message_id)
);

-- Fast lookups: trending queries filter by contract + time
CREATE INDEX IF NOT EXISTS idx_mentions_contract_time
    ON contract_mentions (contract, mentioned_at);

-- Fast lookups: unique-chat counting
CREATE INDEX IF NOT EXISTS idx_mentions_contract_chat_time
    ON contract_mentions (contract, chat_id, mentioned_at);

-- Per-chain trending queries
CREATE INDEX IF NOT EXISTS idx_mentions_chain_time
    ON contract_mentions (chain, mentioned_at);

-- Composite for the main trending aggregation query
CREATE INDEX IF NOT EXISTS idx_mentions_chain_time_contract
    ON contract_mentions (chain, mentioned_at, contract, chat_id);

-- ============================================================
-- Optional: alert history (for auditing)
-- ============================================================
CREATE TABLE IF NOT EXISTS alert_history (
    id              BIGSERIAL       PRIMARY KEY,
    contract        TEXT            NOT NULL,
    chain           TEXT            NOT NULL,
    score           DOUBLE PRECISION NOT NULL,
    mention_count   INT             NOT NULL,
    unique_chats    INT             NOT NULL,
    velocity        DOUBLE PRECISION NOT NULL DEFAULT 0,
    alerted_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_alerts_contract_time
    ON alert_history (contract, alerted_at);
