"""
Dataset Extraction Context.

Lightweight context for feature extraction that doesn't require BuildSample.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from pymongo.database import Database

from app.models.entities.imported_repository import ImportedRepository
from app.models.entities.workflow_run import WorkflowRunRaw


class ExtractionStatus(str, Enum):
    """Status of feature extraction."""
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class DatasetExtractionContext:
    """
    Context for dataset feature extraction.
    
    This is a lightweight context that doesn't require BuildSample.
    It holds all the necessary data for extracting features from a single build.
    """
    # Core data
    repo: ImportedRepository
    workflow_run: WorkflowRunRaw
    db: Database
    
    # Build info (from workflow_run)
    commit_sha: str = ""
    build_number: int = 0
    build_status: Optional[str] = None
    
    # Source languages for diff/snapshot analysis
    source_languages: List[str] = field(default_factory=list)
    
    # Extracted features
    features: Dict[str, Any] = field(default_factory=dict)
    
    # Errors and warnings
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Build stats (populated by git extractor for use by other extractors)
    git_all_built_commits: List[str] = field(default_factory=list)
    tr_prev_build: Optional[int] = None
    gh_build_started_at: Optional[Any] = None
    gh_pr_created_at: Optional[Any] = None
    
    def __post_init__(self):
        """Initialize from workflow_run."""
        self.commit_sha = self.workflow_run.head_sha or ""
        self.build_number = self.workflow_run.run_number or 0
        self.build_status = self.workflow_run.conclusion
        self.gh_build_started_at = self.workflow_run.created_at
        
        # Extract PR info from payload
        payload = self.workflow_run.raw_payload or {}
        pull_requests = payload.get("pull_requests", [])
        if pull_requests:
            pr_data = pull_requests[0]
            self.gh_pr_created_at = pr_data.get("created_at")
    
    def add_feature(self, name: str, value: Any):
        """Add an extracted feature."""
        self.features[name] = value
    
    def add_features(self, features: Dict[str, Any]):
        """Add multiple features."""
        self.features.update(features)
    
    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        """Add a warning message."""
        self.warnings.append(warning)
    
    def has_errors(self) -> bool:
        """Check if there are any errors."""
        return len(self.errors) > 0
    
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return len(self.warnings) > 0
