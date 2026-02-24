"""
SQLAlchemy models for X Persona.
"""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Integer, DateTime, JSON
from app.database import Base


class ProfileRequest(Base):
    """A public request for a persona analysis (not yet analyzed)."""
    __tablename__ = "profile_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Profile(Base):
    """A cached persona analysis for an X username."""
    __tablename__ = "profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    display_name = Column(String(100), nullable=True)
    profile_image_url = Column(String(500), nullable=True)
    bio = Column(String(500), nullable=True)
    membership_count = Column(Integer, default=0)
    memberships = Column(JSON, nullable=False, default=list)  # [{name, owner, id}, ...]
    word_scores = Column(JSON, nullable=False, default=dict)  # {word: score, ...}
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                        onupdate=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Profile @{self.username} ({self.membership_count} lists)>"

    @property
    def is_stale(self):
        """Check if this profile needs refreshing based on cache TTL."""
        import os
        ttl_days = int(os.getenv("CACHE_TTL_DAYS", "7"))
        age = datetime.now(timezone.utc) - self.updated_at.replace(tzinfo=timezone.utc)
        return age.days >= ttl_days
