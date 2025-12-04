"""
DTOs for Custom Dataset Builder.

Request/Response models for dataset job API.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ====================
# Request DTOs
# ====================

class DatasetJobCreateRequest(BaseModel):
    """Request to create a new dataset job."""
    
    repo_url: str = Field(
        ..., 
        description="GitHub repository URL",
        examples=["https://github.com/apache/maven"]
    )
    max_builds: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000,
        description="Maximum number of builds to process (newest first). None = all builds."
    )
    feature_ids: List[str] = Field(
        ...,
        min_length=1,
        description="List of feature IDs to extract",
        examples=[["507f1f77bcf86cd799439011", "507f1f77bcf86cd799439012"]]
    )
    include_metadata: bool = Field(
        default=True,
        description="Include build metadata columns (commit_sha, build_number, build_status)"
    )
    source_languages: List[str] = Field(
        default_factory=list,
        description="Source languages for the repository (required for some features)",
        examples=[["python", "java"]]
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "repo_url": "https://github.com/apache/maven",
                "max_builds": 500,
                "feature_ids": [
                    "507f1f77bcf86cd799439011",
                    "507f1f77bcf86cd799439012",
                ],
                "source_languages": ["java"],
                "include_metadata": True
            }
        }


# ====================
# Response DTOs
# ====================

class FeatureDefinitionResponse(BaseModel):
    """Feature definition for frontend display."""
    
    id: str  # MongoDB ObjectId as string
    slug: str  # Unique name like 'tr_log_tests_run_sum'
    name: str  # Display name
    description: str
    category: str
    data_type: str
    is_ml_feature: bool
    dependencies: List[str] = []  # List of feature IDs
    extractor_node: str
    requires_clone: bool
    requires_log: bool
    
    class Config:
        from_attributes = True


class FeatureCategoryResponse(BaseModel):
    """Grouped features by category."""
    
    category: str
    display_name: str
    features: List[FeatureDefinitionResponse]


class AvailableFeaturesResponse(BaseModel):
    """Response listing available features grouped by category."""
    
    categories: List[FeatureCategoryResponse]
    total_features: int
    ml_features_count: int
    default_features: List[str] = []  # Features always included (not shown in UI)
    features_requiring_source_languages: List[str] = []  # Features that need source_languages


class ResolvedDependenciesResponse(BaseModel):
    """Response showing resolved dependencies."""
    
    selected_feature_ids: List[str]  # Input feature IDs
    resolved_feature_ids: List[str]  # All feature IDs including dependencies
    resolved_feature_names: List[str]  # Feature names for display
    required_nodes: List[str]
    requires_clone: bool
    requires_log_collection: bool
    requires_source_languages: bool = False  # Whether source_languages must be set
    features_needing_source_languages: List[str] = []  # Which features need it


class DatasetJobResponse(BaseModel):
    """Response for a dataset job."""
    
    id: str
    user_id: str
    repo_url: str
    max_builds: Optional[int]
    selected_features: List[str]
    resolved_features: List[str]
    required_nodes: List[str]
    
    # Progress
    status: str
    current_phase: str
    total_builds: int
    processed_builds: int
    failed_builds: int
    progress_percent: float
    
    # Output
    output_file_path: Optional[str]
    output_file_size: Optional[int]
    output_row_count: Optional[int]
    download_count: int
    
    # Timestamps
    created_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    
    # Error
    error_message: Optional[str]
    
    class Config:
        from_attributes = True


class DatasetJobListResponse(BaseModel):
    """Paginated list of dataset jobs."""
    
    items: List[DatasetJobResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class DatasetJobCreatedResponse(BaseModel):
    """Response after creating a dataset job."""
    
    job_id: str
    message: str
    status: str
    estimated_time_minutes: Optional[float]


class DownloadUrlResponse(BaseModel):
    """Response with download URL."""
    
    download_url: str
    filename: str
    file_size: int
    expires_at: Optional[datetime]
