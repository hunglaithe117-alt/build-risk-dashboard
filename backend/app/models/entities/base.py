from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field


def validate_object_id(v: Any) -> ObjectId | None:
    """Validate and convert to ObjectId for entity models."""
    if v is None:
        return None
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        return ObjectId(v)
    raise ValueError(f"Invalid ObjectId: {v}")


# PyObjectId for entities - converts str to ObjectId
PyObjectId = Annotated[ObjectId, BeforeValidator(validate_object_id)]


class BaseEntity(BaseModel):
    """Base entity with common fields for all database entities"""

    id: Optional[ObjectId] = Field(None, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    class Config:
        populate_by_name = True
        arbitrary_types_allowed = True

    def to_mongo(self):
        """Convert to MongoDB document"""
        return self.model_dump(by_alias=True, exclude_none=True)

    def mark_updated(self):
        """Mark entity as updated with current timestamp"""
        self.updated_at = datetime.now(timezone.utc)
        return self
