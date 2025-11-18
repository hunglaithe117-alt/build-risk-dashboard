"""User and authentication DTOs"""

from datetime import datetime
from typing import Annotated, Any, List, Literal, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# Custom validator for MongoDB ObjectId
def validate_object_id(v: Any) -> str:
    """Validate and convert ObjectId to string."""
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


class UserResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    email: str
    name: Optional[str] = None
    role: Literal["admin", "user"] = "user"
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class OAuthIdentityResponse(BaseModel):
    id: PyObjectId = Field(..., alias="_id")
    user_id: PyObjectId
    provider: str
    external_user_id: str
    scopes: Optional[str] = None
    token_expires_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class UserRoleDefinition(BaseModel):
    role: str
    description: str
    permissions: List[str]
    admin_only: bool = False
