"""
Dataset Sample Entity.

Stores extracted features for Custom Dataset Builder jobs.
This is separate from BuildSample to avoid polluting the main import flow.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import Field

from .base import BaseEntity, PyObjectId


class DatasetSample(BaseEntity):
    """
    A single sample (row) in a dataset extraction job.
    
    Stores features extracted for one workflow run in a flexible schema
    since different jobs may extract different feature sets.
    """
    
    # References
    job_id: PyObjectId = Field(..., description="Reference to DatasetJob")
    repo_id: PyObjectId = Field(..., description="Reference to ImportedRepository")
    workflow_run_id: int = Field(..., description="GitHub workflow run ID")
    
    # Build metadata
    commit_sha: str = Field(..., description="Git commit SHA")
    build_number: int = Field(..., description="Workflow run number")
    build_status: Optional[str] = Field(default=None, description="Build conclusion (success/failure)")
    build_created_at: Optional[datetime] = Field(default=None, description="When the build was created")
    
    # Extraction status
    status: str = Field(default="pending", description="pending, completed, failed, skipped")
    error_message: Optional[str] = Field(default=None, description="Error message if extraction failed")
    
    # Extracted features - flexible dict to store any feature set
    features: Dict[str, Any] = Field(
        default_factory=dict, 
        description="Extracted feature values keyed by feature name"
    )
    
    # Timestamps
    extracted_at: Optional[datetime] = Field(
        default=None, 
        description="When features were extracted"
    )

    class Settings:
        name = "dataset_samples"
        
    class Config:
        json_schema_extra = {
            "example": {
                "job_id": "507f1f77bcf86cd799439011",
                "repo_id": "507f1f77bcf86cd799439012",
                "workflow_run_id": 12345678,
                "commit_sha": "abc123def456",
                "build_number": 42,
                "build_status": "success",
                "status": "completed",
                "features": {
                    "tr_build_id": 12345678,
                    "gh_project_name": "owner/repo",
                    "git_diff_src_churn": 150,
                    "tr_log_tests_run_sum": 42,
                },
                "extracted_at": "2025-01-15T10:30:00Z",
            }
        }
