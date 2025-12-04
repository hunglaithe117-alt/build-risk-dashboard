"""
Dataset Job Entity.

Represents a user request to build a custom dataset from a GitHub repository.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from bson import ObjectId
from pydantic import Field

from .base import BaseEntity


class DatasetJobStatus(str, Enum):
    """Status of a dataset job."""
    PENDING = "pending"           # Job created, waiting to start
    FETCHING_RUNS = "fetching_runs"  # Fetching workflow runs from GitHub
    PROCESSING = "processing"     # Extracting features
    EXPORTING = "exporting"       # Generating CSV
    COMPLETED = "completed"       # Done, CSV available
    FAILED = "failed"             # Job failed
    CANCELLED = "cancelled"       # User cancelled


class DatasetJob(BaseEntity):
    """
    A job to build a custom dataset from a GitHub repository.
    
    This is independent from the main import flow - it's a one-off
    extraction job that produces a CSV file.
    """
    
    # User who created the job
    user_id: ObjectId = Field(..., description="User who created this job")
    
    # Repository info (not necessarily imported)
    repo_full_name: str = Field(default="", description="GitHub repo full name (owner/repo)")
    repo_url: str = Field(default="", description="GitHub repo URL")
    installation_id: Optional[int] = Field(default=None, description="GitHub App installation ID if private")
    is_public: bool = Field(default=True, description="Whether the repo is public")
    
    # Job configuration
    max_builds: Optional[int] = Field(
        default=None, 
        description="Maximum builds to fetch (None = all available)"
    )
    selected_features: List[str] = Field(
        default_factory=list,
        description="Feature names selected by user"
    )
    resolved_features: List[str] = Field(
        default_factory=list,
        description="All features including dependencies"
    )
    required_nodes: List[str] = Field(
        default_factory=list,
        description="Extractor nodes that need to run"
    )
    required_resources: List[str] = Field(
        default_factory=list,
        description="Resources that need to be initialized"
    )
    
    # Resource requirements (for optimization)
    requires_clone: bool = Field(default=False, description="Whether git clone is needed")
    requires_log: bool = Field(default=False, description="Whether log collection is needed")
    source_languages: List[str] = Field(
        default_factory=list,
        description="Source languages for the repository (for language-dependent features)"
    )
    
    # Status tracking
    status: DatasetJobStatus = Field(default=DatasetJobStatus.PENDING)
    error_message: Optional[str] = Field(default=None)
    
    # Progress tracking
    total_builds: int = Field(default=0, description="Total builds to process")
    processed_builds: int = Field(default=0, description="Builds processed so far")
    failed_builds: int = Field(default=0, description="Builds that failed extraction")
    current_phase: str = Field(default="", description="Current processing phase")
    
    # Timing
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    
    # Output
    output_file_path: Optional[str] = Field(default=None, description="Path to generated CSV")
    output_file_size: Optional[int] = Field(default=None, description="File size in bytes")
    output_row_count: int = Field(default=0, description="Number of rows in CSV")
    
    # Download tracking
    download_url: Optional[str] = Field(default=None, description="Signed URL for download")
    download_expires_at: Optional[datetime] = Field(default=None)
    download_count: int = Field(default=0)
    
    class Config:
        use_enum_values = True
