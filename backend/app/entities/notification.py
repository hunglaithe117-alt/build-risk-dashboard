"""Notification entity for in-app notifications."""

from enum import Enum
from typing import Optional

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId


class NotificationType(str, Enum):
    """Types of notifications."""

    PIPELINE_COMPLETED = "pipeline_completed"
    PIPELINE_FAILED = "pipeline_failed"
    DATASET_IMPORT_COMPLETED = "dataset_import_completed"
    DATASET_VALIDATION_COMPLETED = "dataset_validation_completed"
    DATASET_ENRICHMENT_COMPLETED = "dataset_enrichment_completed"
    RATE_LIMIT_WARNING = "rate_limit_warning"
    RATE_LIMIT_EXHAUSTED = "rate_limit_exhausted"
    SYSTEM = "system"


class Notification(BaseEntity):
    """In-app notification for users."""

    user_id: PyObjectId = Field(..., description="User who receives this notification")
    type: NotificationType = Field(..., description="Type of notification")
    title: str = Field(..., description="Notification title")
    message: str = Field(..., description="Notification message body")
    is_read: bool = Field(default=False, description="Whether notification has been read")
    link: Optional[str] = Field(default=None, description="URL to navigate on click")
    metadata: Optional[dict] = Field(default=None, description="Extra context data")
