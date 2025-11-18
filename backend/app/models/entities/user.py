"""User entity - represents a user account in the database"""

from datetime import datetime
from typing import Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, Field


class User(BaseModel):
    """User entity stored in MongoDB"""

    id: Optional[ObjectId] = Field(None, alias="_id")
    email: str
    name: Optional[str] = None
    role: Literal["admin", "user"] = "user"
    created_at: datetime

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True
