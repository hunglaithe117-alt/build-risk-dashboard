"""User entity - represents a user account in the database"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import Field

from .base import BaseEntity


class User(BaseEntity):
    email: str
    name: str | None = None
    role: Literal["admin", "user"] = "user"

    # GitHub repo membership sync (for RBAC)
    # Stores list of repo full_names the user has access to on GitHub
    github_accessible_repos: List[str] = Field(default_factory=list)
    github_repos_synced_at: Optional[datetime] = None
