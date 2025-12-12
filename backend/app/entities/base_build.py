from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from .base import BaseEntity, PyObjectId


class ExtractionStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class BaseBuildSample(BaseEntity):
    """
    Base class for builds that can be processed by the FeaturePipeline.
    Both ModelBuild (for ML prediction) and EnrichmentBuild (for dataset enrichment)
    """

    repo_id: PyObjectId
    workflow_run_id: Optional[int] = None
    head_sha: Optional[str] = None
    build_number: Optional[int] = None
    build_created_at: Optional[datetime] = None

    extraction_status: ExtractionStatus = ExtractionStatus.PENDING
    error_message: Optional[str] = None
    is_missing_commit: bool = False

    features: Dict = {}

    class Config:
        use_enum_values = True
