-- ==============================================================================
-- Solana Trading Bot - Database Initialization
-- ==============================================================================
-- This script creates the required tables for signal PnL tracking

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

-- Log initialization
DO $$
BEGIN
    RAISE NOTICE 'Database initialized successfully for Solana Trading Bot';
END $$;
