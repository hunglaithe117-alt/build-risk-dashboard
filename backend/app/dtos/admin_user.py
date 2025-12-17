"""DTOs for Admin User Management API."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.entities.base import PyObjectIdStr


class AdminUserResponse(BaseModel):
    """User response for admin endpoints."""

    id: PyObjectIdStr = Field(..., alias="_id")
    email: str
    name: Optional[str] = None
    role: Literal["admin", "user"]
    created_at: datetime

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AdminUserListResponse(BaseModel):
    """Response with list of users."""

    items: List[AdminUserResponse]
    total: int


class AdminUserCreateRequest(BaseModel):
    """Request to create a new user."""

    email: str = Field(..., description="User email address")
    name: Optional[str] = Field(None, description="User display name")
    role: Literal["admin", "user"] = Field("user", description="User role")


class AdminUserUpdateRequest(BaseModel):
    """Request to update user profile."""

    email: Optional[str] = Field(None, description="New email address")
    name: Optional[str] = Field(None, description="New display name")


class AdminUserRoleUpdateRequest(BaseModel):
    """Request to update user role."""

    role: Literal["admin", "user"] = Field(..., description="New role")
