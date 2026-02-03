"""Database schema definitions."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Text,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base

from src.constants import RiskRating
from src.models import AnalysisStatus, EventSource

Base = declarative_base()


class TokenAnalysisRecord(Base):
    """Stores token analysis results."""

    __tablename__ = "token_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), unique=True, nullable=False, index=True)
    token_address = Column(String(42), nullable=False, index=True)

    # Token info
    symbol = Column(String(32))
    name = Column(String(128))
    chain_id = Column(Integer, default=8453)

    # Detection
    source = Column(String(32))  # EventSource value
    detected_at = Column(DateTime, nullable=False)

    # Analysis results
    risk_rating = Column(String(16))  # RiskRating value
    fdv_usd = Column(Float, default=0)
    liquidity_usd = Column(Float, default=0)
    holder_count = Column(Integer, default=0)
    top_10_holder_pct = Column(Float, default=0)

    # Dev info
    dev_twitter_handle = Column(String(32))
    dev_twitter_followers = Column(Integer, default=0)
    dev_is_anonymous = Column(Boolean, default=True)

    # Contract info
    deployer_address = Column(String(42))
    is_honeypot = Column(Boolean, default=False)
    is_renounced = Column(Boolean, default=False)

    # Status
    status = Column(String(32), default="pending")  # AnalysisStatus value
    error_message = Column(Text)

    # Telegram
    telegram_message_id = Column(Integer)
    published_at = Column(DateTime)

    # Full data (JSON blobs)
    contract_analysis_json = Column(JSON)
    dev_profile_json = Column(JSON)
    onchain_metrics_json = Column(JSON)
    breakdown_json = Column(JSON)

    # Metadata
    processing_time_seconds = Column(Float, default=0)
    confidence_score = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Indexes
    __table_args__ = (
        Index("idx_token_symbol", "symbol"),
        Index("idx_risk_rating", "risk_rating"),
        Index("idx_status", "status"),
        Index("idx_detected_at", "detected_at"),
    )


class BlacklistRecord(Base):
    """Stores blacklisted addresses and devs."""

    __tablename__ = "blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    identifier = Column(String(128), unique=True, nullable=False, index=True)
    category = Column(String(32), nullable=False)  # wallet, contract, twitter
    reason = Column(Text, nullable=False)
    added_by = Column(String(64), default="system")
    added_at = Column(DateTime, default=datetime.utcnow)

    # Evidence
    evidence_json = Column(JSON)

    __table_args__ = (
        Index("idx_category", "category"),
    )


class AnalysisStatsRecord(Base):
    """Stores daily analysis statistics."""

    __tablename__ = "analysis_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, index=True)

    # Counts
    total_detected = Column(Integer, default=0)
    total_analyzed = Column(Integer, default=0)
    total_published = Column(Integer, default=0)
    total_rejected = Column(Integer, default=0)
    total_failed = Column(Integer, default=0)

    # By rating
    rating_green = Column(Integer, default=0)
    rating_yellow = Column(Integer, default=0)
    rating_orange = Column(Integer, default=0)
    rating_red = Column(Integer, default=0)

    # By source
    source_chain = Column(Integer, default=0)
    source_moltbook = Column(Integer, default=0)
    source_twitter = Column(Integer, default=0)
    source_manual = Column(Integer, default=0)

    # Performance
    avg_processing_time = Column(Float, default=0)
    avg_confidence_score = Column(Float, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
