from datetime import datetime
from typing import Dict

from pydantic import Field

from app.entities.base import BaseEntity, PyObjectId


class ScanResult(BaseEntity):
    """Stores the actual metrics/results from a SonarQube scan."""

    repo_id: PyObjectId = Field(...)
    job_id: PyObjectId = Field(...)  # Reference to ScanJob
    sonar_project_key: str = Field(...)
    metrics: Dict[str, float | int | str] = Field(default_factory=dict)

    class Config:
        json_encoders = {datetime: lambda dt: dt.isoformat()}
