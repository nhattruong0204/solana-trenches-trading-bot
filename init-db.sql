-- ==============================================================================
-- Solana Trading Bot - Database Initialization
-- ==============================================================================
-- This script creates the required tables for signal PnL tracking

-- Enable pg_trgm extension for fast LIKE queries (Grafana dashboard)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Create raw_telegram_messages table for storing signals and alerts
CREATE TABLE IF NOT EXISTS raw_telegram_messages (
    id SERIAL PRIMARY KEY,
    telegram_message_id BIGINT NOT NULL,
    telegram_chat_id BIGINT NOT NULL,
    raw_text TEXT,
    raw_json JSONB,
    message_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    chat_title TEXT,
    sender_id BIGINT,
    sender_username TEXT,
    source_bot TEXT DEFAULT 'trenches',
    is_parsed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ingested_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Unique constraint to prevent duplicates
    UNIQUE(telegram_message_id, telegram_chat_id)
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_raw_telegram_message_timestamp
    ON raw_telegram_messages(message_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_telegram_chat_id
    ON raw_telegram_messages(telegram_chat_id);
CREATE INDEX IF NOT EXISTS idx_raw_telegram_source_bot
    ON raw_telegram_messages(source_bot);

-- Performance indexes for Grafana dashboard queries
CREATE INDEX IF NOT EXISTS idx_rtm_chat_title_timestamp
    ON raw_telegram_messages(chat_title, message_timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_rtm_raw_json_reply
    ON raw_telegram_messages((raw_json->>'reply_to_msg_id'));

-- Trigram index for fast LIKE '%pattern%' queries (requires pg_trgm)
CREATE INDEX IF NOT EXISTS idx_rtm_raw_text_trgm
    ON raw_telegram_messages USING gin (raw_text gin_trgm_ops);

-- ==============================================================================
-- Materialized View for Daily Signal Stats (Grafana Performance)
-- ==============================================================================
-- Pre-aggregated daily stats to avoid expensive real-time calculations

CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_signal_stats AS
WITH signals AS (
    SELECT 
        DATE(message_timestamp) AS day,
        chat_title,
        telegram_message_id,
        CASE 
            WHEN chat_title LIKE '%VOLUME%' THEN 'VOLSM'
            ELSE 'MAIN'
        END AS channel
    FROM raw_telegram_messages
    WHERE raw_text LIKE '%APE SIGNAL DETECTED%'
       OR raw_text LIKE '%NEW-LAUNCH%'
       OR raw_text LIKE '%MID-SIZED%'
),
profit_alerts AS (
    SELECT DISTINCT (raw_json->>'reply_to_msg_id')::BIGINT AS signal_id
    FROM raw_telegram_messages
    WHERE raw_text LIKE '%PROFIT ALERT%'
      AND raw_json->>'reply_to_msg_id' IS NOT NULL
)
SELECT 
    s.day,
    s.channel,
    COUNT(*) AS total_signals,
    COUNT(pa.signal_id) AS winning_signals,
    ROUND(COUNT(pa.signal_id)::NUMERIC / NULLIF(COUNT(*), 0) * 100, 2) AS win_rate_pct
FROM signals s
LEFT JOIN profit_alerts pa ON pa.signal_id = s.telegram_message_id
GROUP BY s.day, s.channel;

-- Unique index for fast refresh and lookups
CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_stats_day_channel 
    ON mv_daily_signal_stats(day, channel);

-- ==============================================================================
-- Channel State Table - Tracks sync cursors per channel
-- ==============================================================================
-- This is the "belt and suspenders" approach to prevent duplicate processing

CREATE TABLE IF NOT EXISTS telegram_channel_state (
    id SERIAL PRIMARY KEY,
    channel_id BIGINT NOT NULL UNIQUE,
    channel_name TEXT NOT NULL,
    last_message_id BIGINT NOT NULL DEFAULT 0,
    last_processed_at TIMESTAMP WITH TIME ZONE,
    bootstrap_completed BOOLEAN DEFAULT FALSE,
    bootstrap_completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_channel_state_channel_id 
    ON telegram_channel_state(channel_id);

-- Grant permissions
GRANT ALL PRIVILEGES ON TABLE raw_telegram_messages TO postgres;
GRANT USAGE, SELECT ON SEQUENCE raw_telegram_messages_id_seq TO postgres;
GRANT ALL PRIVILEGES ON TABLE telegram_channel_state TO postgres;
GRANT USAGE, SELECT ON SEQUENCE telegram_channel_state_id_seq TO postgres;

-- Grant permissions on materialized view
GRANT SELECT ON mv_daily_signal_stats TO postgres;

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully for Solana Trading Bot';
    RAISE NOTICE 'pg_trgm extension enabled for fast LIKE queries';
    RAISE NOTICE 'Materialized view mv_daily_signal_stats created';
    RAISE NOTICE 'Run REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_signal_stats; periodically';
END $$;
