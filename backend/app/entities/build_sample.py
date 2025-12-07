from datetime import datetime
from typing import List, Optional

from .base import BaseEntity, PyObjectId


class BuildSample(BaseEntity):
    repo_id: PyObjectId
    workflow_run_id: int
    status: str = "pending"  # pending, completed, failed
    error_message: str | None = None
    is_missing_commit: bool = False

    # Dynamic Features
    features: dict = {}

    tr_build_id: int | None = None
    tr_build_number: int | None = None
    tr_original_commit: str | None = None
    git_trigger_commit: str | None = None
    git_branch: str | None = None
    tr_jobs: List[int] = []
    tr_status: str | None = None
    tr_duration: float | None = None
    tr_log_num_jobs: int | None = None    
    ci_provider: str | None = None
    gh_build_started_at: datetime | None = None
    gh_lang: str | None = None
    tr_log_tests_run_sum: int | None = None

    # Operational Status
    sonar_scan_status: str | None = None

    class Config:
        populate_by_name = True
