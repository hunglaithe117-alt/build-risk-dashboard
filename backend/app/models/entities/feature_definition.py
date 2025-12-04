"""
Feature Definition Entity.

Stores metadata about each feature that can be extracted by the pipeline.
This provides a single source of truth for feature documentation and configuration.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import Field

from .base import BaseEntity


class FeatureSource(str, Enum):
    """Source where the feature is extracted from."""
    BUILD_LOG = "build_log"           # CI build logs
    GIT_REPO = "git_repo"             # Git repository (commits, diffs)
    GITHUB_API = "github_api"         # GitHub REST/GraphQL API
    WORKFLOW_RUN = "workflow_run"     # GitHub Actions workflow run data
    DERIVED = "derived"               # Calculated from other features
    METADATA = "metadata"             # Repository/build metadata


class FeatureDataType(str, Enum):
    """Data type of the feature value."""
    INTEGER = "integer"
    FLOAT = "float"
    STRING = "string"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    LIST_STRING = "list_string"
    LIST_INTEGER = "list_integer"


class FeatureCategory(str, Enum):
    """Logical category for grouping features."""
    BUILD_LOG = "build_log"           # tr_* features
    GIT_DIFF = "git_diff"             # git_diff_*, gh_diff_* features
    GIT_HISTORY = "git_history"       # git_prev_*, git_all_* features
    REPO_SNAPSHOT = "repo_snapshot"   # gh_repo_*, gh_sloc_* features
    TEAM = "team"                     # gh_team_*, gh_by_core_* features
    DISCUSSION = "discussion"         # gh_num_*_comments features
    PR_INFO = "pr_info"               # gh_is_pr, gh_pr_*, gh_pull_req_* features
    METADATA = "metadata"             # gh_project_name, ci_provider, etc.


class FeatureDefinition(BaseEntity):
    """
    Definition and metadata for a single feature.
    
    This entity stores:
    - Feature identification (name, display name, description)
    - Source and extraction info
    - Dependencies on other features
    - Data type and validation
    - Active/deprecated status
    """
    
    # Identification
    name: str = Field(..., description="Unique feature name (e.g., 'tr_log_tests_run_sum')")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(default="", description="Detailed description of the feature")
    
    # Categorization
    category: FeatureCategory = Field(..., description="Logical category")
    source: FeatureSource = Field(..., description="Primary data source")
    extractor_node: str = Field(..., description="Name of the FeatureNode that extracts this")
    
    # Dependencies
    depends_on_features: List[str] = Field(
        default_factory=list,
        description="Features that must be extracted before this one"
    )
    depends_on_resources: List[str] = Field(
        default_factory=list,
        description="Resources required (git_repo, github_client, etc.)"
    )
    
    # Data type info
    data_type: FeatureDataType = Field(..., description="Data type of the feature value")
    nullable: bool = Field(default=True, description="Whether the value can be null")
    default_value: Optional[str] = Field(
        default=None, 
        description="Default value if extraction fails (as string)"
    )
    
    # Status
    is_active: bool = Field(default=True, description="Whether this feature is currently active")
    is_deprecated: bool = Field(default=False, description="Whether this feature is deprecated")
    deprecated_reason: Optional[str] = Field(default=None, description="Reason for deprecation")
    replaced_by: Optional[str] = Field(default=None, description="Feature that replaces this one")
    
    # ML/Analysis metadata
    is_ml_feature: bool = Field(
        default=True, 
        description="Whether this feature is used in ML models"
    )
    feature_importance: Optional[float] = Field(
        default=None, 
        description="Importance score from ML model (0-1)"
    )
    
    # Versioning
    version: str = Field(default="1.0", description="Feature definition version")
    added_in_version: str = Field(default="1.0", description="Pipeline version when added")
    
    # Documentation
    example_value: Optional[str] = Field(default=None, description="Example value")
    unit: Optional[str] = Field(default=None, description="Unit of measurement if applicable")
    
    class Config:
        use_enum_values = True
