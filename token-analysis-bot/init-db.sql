-- Database initialization script for token analysis bot

-- Create database (run as postgres superuser)
-- CREATE DATABASE token_analysis;

-- Connect to the database
-- \c token_analysis

-- Token analyses table
CREATE TABLE IF NOT EXISTS token_analyses (
    id SERIAL PRIMARY KEY,
    job_id VARCHAR(64) UNIQUE NOT NULL,
    token_address VARCHAR(42) NOT NULL,
    symbol VARCHAR(32),
    name VARCHAR(128),
    chain_id INTEGER DEFAULT 8453,

    -- Detection source
    source VARCHAR(32),
    detected_at TIMESTAMP NOT NULL,

    -- Risk assessment
    risk_rating VARCHAR(16),
    fdv_usd FLOAT DEFAULT 0,
    liquidity_usd FLOAT DEFAULT 0,
    holder_count INTEGER DEFAULT 0,
    top_10_holder_pct FLOAT DEFAULT 0,

    -- Developer info
    dev_twitter_handle VARCHAR(32),
    dev_twitter_followers INTEGER DEFAULT 0,
    dev_is_anonymous BOOLEAN DEFAULT TRUE,

    -- Contract info
    deployer_address VARCHAR(42),
    is_honeypot BOOLEAN DEFAULT FALSE,
    is_renounced BOOLEAN DEFAULT FALSE,

    -- Processing status
    status VARCHAR(32) DEFAULT 'pending',
    error_message TEXT,

    -- Telegram delivery
    telegram_message_id INTEGER,
    published_at TIMESTAMP,

    -- Full JSON data
    contract_analysis_json JSONB,
    dev_profile_json JSONB,
    onchain_metrics_json JSONB,
    breakdown_json JSONB,

    -- Metrics
    processing_time_seconds FLOAT DEFAULT 0,
    confidence_score FLOAT DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_token_address ON token_analyses(token_address);
CREATE INDEX IF NOT EXISTS idx_symbol ON token_analyses(symbol);
CREATE INDEX IF NOT EXISTS idx_status ON token_analyses(status);
CREATE INDEX IF NOT EXISTS idx_risk_rating ON token_analyses(risk_rating);
CREATE INDEX IF NOT EXISTS idx_detected_at ON token_analyses(detected_at);
CREATE INDEX IF NOT EXISTS idx_created_at ON token_analyses(created_at);

-- Blacklist table
CREATE TABLE IF NOT EXISTS blacklist (
    id SERIAL PRIMARY KEY,
    identifier VARCHAR(128) UNIQUE NOT NULL,
    category VARCHAR(32) NOT NULL,  -- 'wallet', 'contract', 'twitter'
    reason TEXT NOT NULL,
    added_by VARCHAR(64) DEFAULT 'system',
    added_at TIMESTAMP DEFAULT NOW(),
    evidence_json JSONB
);

CREATE INDEX IF NOT EXISTS idx_blacklist_identifier ON blacklist(identifier);
CREATE INDEX IF NOT EXISTS idx_blacklist_category ON blacklist(category);

-- Daily statistics table
CREATE TABLE IF NOT EXISTS analysis_stats (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,

    -- Counts
    total_detected INTEGER DEFAULT 0,
    total_analyzed INTEGER DEFAULT 0,
    total_published INTEGER DEFAULT 0,
    total_rejected INTEGER DEFAULT 0,
    total_failed INTEGER DEFAULT 0,

    -- By risk rating
    rating_green INTEGER DEFAULT 0,
    rating_yellow INTEGER DEFAULT 0,
    rating_orange INTEGER DEFAULT 0,
    rating_red INTEGER DEFAULT 0,

    -- By source
    source_chain INTEGER DEFAULT 0,
    source_moltbook INTEGER DEFAULT 0,
    source_twitter INTEGER DEFAULT 0,
    source_manual INTEGER DEFAULT 0,

    -- Performance
    avg_processing_time FLOAT DEFAULT 0,
    avg_confidence_score FLOAT DEFAULT 0,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stats_date ON analysis_stats(date);

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger for auto-updating updated_at
DROP TRIGGER IF EXISTS update_token_analyses_updated_at ON token_analyses;
CREATE TRIGGER update_token_analyses_updated_at
    BEFORE UPDATE ON token_analyses
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Utility views

-- Recent published analyses
CREATE OR REPLACE VIEW recent_published AS
SELECT
    job_id,
    token_address,
    symbol,
    risk_rating,
    fdv_usd,
    liquidity_usd,
    holder_count,
    dev_twitter_handle,
    published_at
FROM token_analyses
WHERE status = 'published'
ORDER BY published_at DESC
LIMIT 100;

-- Daily summary
CREATE OR REPLACE VIEW daily_summary AS
SELECT
    DATE(created_at) as analysis_date,
    COUNT(*) as total_analyzed,
    COUNT(*) FILTER (WHERE status = 'published') as published,
    COUNT(*) FILTER (WHERE risk_rating = 'green') as green,
    COUNT(*) FILTER (WHERE risk_rating = 'yellow') as yellow,
    COUNT(*) FILTER (WHERE risk_rating = 'orange') as orange,
    COUNT(*) FILTER (WHERE risk_rating = 'red') as red,
    AVG(processing_time_seconds) as avg_processing_time
FROM token_analyses
GROUP BY DATE(created_at)
ORDER BY analysis_date DESC;

-- Grant permissions (adjust username as needed)
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO your_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_user;
