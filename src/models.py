from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from db.database import Base
from utils.time_utils import utc_now


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), nullable=False, index=True)  # 'X', 'TikTok'
    username = Column(String(120), nullable=True, index=True)
    display_name = Column(String(120), nullable=True)
    token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    cookies_encrypted = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    refresh_token_expiry = Column(DateTime, nullable=True)
    api_key_encrypted = Column(Text, nullable=True)
    api_secret_encrypted = Column(Text, nullable=True)
    access_token_encrypted = Column(Text, nullable=True)  # OAuth 1.0a access token
    access_token_secret_encrypted = Column(Text, nullable=True)  # OAuth 1.0a access secret
    is_active = Column(Boolean, default=True)
    reply_bot_enabled = Column(Boolean, default=False)
    reply_bot_frequency = Column(Integer, default=15)  # minutes
    auto_reply_enabled = Column(Boolean, default=False)
    last_mention_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    style_profile = relationship("StyleProfile", uselist=False, back_populates="account", cascade="all, delete-orphan")
    posts = relationship("PostHistory", back_populates="account", cascade="all, delete-orphan")
    scheduled = relationship("ScheduledPost", back_populates="account", cascade="all, delete-orphan")
    memory_chunks = relationship("MemoryChunk", back_populates="account", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="account")


class StyleProfile(Base):
    __tablename__ = "style_profiles"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, unique=True)
    profile_json = Column(Text, nullable=False, default="{}")
    embedding = Column(Text, nullable=True)
    style_summary = Column(Text, nullable=True)
    common_hashtags = Column(Text, nullable=True)
    avg_post_length = Column(Integer, nullable=True)
    tone = Column(String(40), nullable=True)
    topics = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    account = relationship("Account", back_populates="style_profile")


class PostHistory(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)
    post_id = Column(String(100), nullable=True, index=True)
    content = Column(Text, nullable=False)
    media_urls = Column(Text, nullable=True)
    engagement = Column(Text, nullable=True)  # JSON: likes, replies, retweets, views
    created_at = Column(DateTime, default=utc_now)
    posted_at = Column(DateTime, nullable=True)
    meta_data = Column(Text, nullable=True)
    source = Column(String(40), nullable=True, default="unknown")
    brain_model = Column(String(60), nullable=True)
    generated = Column(Boolean, default=False)
    embedding = Column(Text, nullable=True)
    is_scraped = Column(Boolean, default=False)
    reply_to_id = Column(String(100), nullable=True)
    reply_to_username = Column(String(120), nullable=True)

    account = relationship("Account", back_populates="posts")


class MemoryChunk(Base):
    __tablename__ = "memory_chunks"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    chunk_type = Column(String(40), nullable=False, default="post")  # post, style, context
    content = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)
    similarity_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    account = relationship("Account", back_populates="memory_chunks")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utc_now, index=True)
    action = Column(String(128), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    status = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)
    platform = Column(String(20), nullable=True)

    account = relationship("Account", back_populates="audit_logs")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False, index=True)
    content = Column(Text, nullable=False)
    media_path = Column(Text, nullable=True)
    scheduled_at = Column(DateTime, nullable=False, index=True)
    status = Column(String(20), default="scheduled", index=True)  # scheduled, published, failed, cancelled
    error_message = Column(Text, nullable=True)
    published_at = Column(DateTime, nullable=True)
    post_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utc_now)

    account = relationship("Account", back_populates="scheduled")
