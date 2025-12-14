# Feature Pipeline - Hamilton-based Feature Extraction
# Uses Hamilton DAG framework for feature extraction

from app.pipeline.core.registry import feature_registry, OutputFormat

# Hamilton pipeline
from app.pipeline.hamilton_runner import HamiltonPipeline
from app.pipeline.hamilton_features._inputs import (
    GitHistoryInput,
    GitWorktreeInput,
    RepoInput,
    WorkflowRunInput,
    GitHubClientInput,
)

__all__ = [
    # Core
    "feature_registry",
    "OutputFormat",
    # Hamilton
    "HamiltonPipeline",
    "GitHistoryInput",
    "GitWorktreeInput",
    "RepoInput",
    "WorkflowRunInput",
    "GitHubClientInput",
]
