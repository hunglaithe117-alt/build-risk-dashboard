"""Build DTOs for API requests and responses"""

from datetime import datetime
from typing import Annotated, Any, List, Optional

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


class BuildCreate(BaseModel):
    """Schema for creating a new build"""

    repository: str
    branch: str
    commit_sha: str
    build_number: str
    workflow_name: Optional[str] = None
    status: str
    conclusion: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    url: Optional[str] = None
    logs_url: Optional[str] = None


class BuildResponse(BaseModel):
    """Schema for build response"""

    id: PyObjectId = Field(..., alias="_id")
    repository: str
    branch: str
    commit_sha: str
    build_number: str
    workflow_name: Optional[str] = None
    status: str
    conclusion: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    url: Optional[str] = None
    logs_url: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(populate_by_name=True)


class BuildListItem(BuildResponse):
    """Build item with related analytics"""

    pass


class BuildListResponse(BaseModel):
    """Schema for paginated build list response"""

    total: int
    skip: int
    limit: int
    builds: List[BuildListItem]


class BuildDetailResponse(BuildListItem):
    """Schema for detailed build information including all assessments"""

    pass


BuildListItem.model_rebuild()
BuildDetailResponse.model_rebuild()
