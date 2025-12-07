"""User entity - represents a user account in the database"""

from typing import Literal

from .base import BaseEntity


class User(BaseEntity):
    email: str
    name: str | None = None
    role: Literal["admin", "user"] = "user"
