from __future__ import annotations

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from db.database import Base


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String(20), nullable=False)  # e.g., 'X' or 'TikTok'
    username = Column(String(120), nullable=True)
    token_encrypted = Column(Text, nullable=True)
    refresh_token_encrypted = Column(Text, nullable=True)
    cookies_encrypted = Column(Text, nullable=True)
    token_expiry = Column(DateTime, nullable=True)
    refresh_token_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    style_profile = relationship("StyleProfile", uselist=False, back_populates="account")
    posts = relationship("PostHistory", back_populates="account")
    scheduled = relationship("ScheduledPost", back_populates="account")


class StyleProfile(Base):
    __tablename__ = "style_profiles"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    profile_json = Column(Text, nullable=False, default="{}")
    embedding = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="style_profile")


class PostHistory(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    platform = Column(String(20))
    post_id = Column(String(100), nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    metadata = Column(Text, nullable=True)
    # Enhanced metadata for end-to-end traceability
    source = Column(String(40), nullable=True)
    brain_model = Column(String(60), nullable=True)
    generated = Column(Boolean, default=False)
    # Legacy: new fields to improve debugging/tracing are added above; keep compatibility

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    action = Column(String(128), nullable=False)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    status = Column(String(64), nullable=True)
    details = Column(Text, nullable=True)

    account = relationship("Account", backref="audit_logs")

    account = relationship("Account", back_populates="posts")


class ScheduledPost(Base):
    __tablename__ = "scheduled_posts"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"))
    content = Column(Text, nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(String(20), default="scheduled")
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="scheduled")
