from __future__ import annotations

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from .base import BaseEntity


class User(BaseEntity):
    """User entity with settings embedded."""

    email: str
    name: Optional[str] = None
    role: Literal["admin", "user", "guest"] = "user"
    notification_email: Optional[str] = None
    github_accessible_repos: List[str] = Field(default_factory=list)
    github_repos_synced_at: Optional[datetime] = None
    browser_notifications: bool = Field(default=True, description="Enable browser notifications")

    class Config:
        collection = "users"
        use_enum_values = True
