from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, Field, ConfigDict


def validate_object_id(v: Any) -> ObjectId | None:
    """Validate and convert to ObjectId for entity models."""
    if v is None:
        return None
    if isinstance(v, ObjectId):
        return v
    if isinstance(v, str):
        if not ObjectId.is_valid(v):
            raise ValueError(f"Invalid ObjectId: {v}")
        return ObjectId(v)
    raise ValueError(f"Invalid ObjectId: {v}")


def validate_object_id_str(v: Any) -> str | None:
    """Validate and convert to string for DTOs."""
    if v is None:
        return None
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        if not ObjectId.is_valid(v):
            raise ValueError(f"Invalid ObjectId: {v}")
        return v
    raise ValueError(f"Invalid ObjectId: {v}")


# PyObjectId for entities - converts str to ObjectId (for DB)
PyObjectId = Annotated[ObjectId, BeforeValidator(validate_object_id)]

# PyObjectIdStr for DTOs - converts ObjectId to str (for JSON)
PyObjectIdStr = Annotated[str, BeforeValidator(validate_object_id_str)]


class BaseEntity(BaseModel):
    """Base entity with common fields for all database entities"""

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
        exclude_none=True,  # avoid persisting fields with None (e.g., _id)
        protected_namespaces=(),  # Allow model_ prefix in field names
    )

    id: Optional[PyObjectId] = Field(None, alias="_id")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    def to_mongo(self):
        """Convert to MongoDB document"""
        return self.model_dump(by_alias=True, exclude_none=True)

    def mark_updated(self):
        """Mark entity as updated with current timestamp"""
        self.updated_at = datetime.now(timezone.utc)
        return self
