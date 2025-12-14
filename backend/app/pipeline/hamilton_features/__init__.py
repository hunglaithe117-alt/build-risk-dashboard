"""
Hamilton-based Feature Extraction.

This package uses Hamilton for DAG-based feature extraction with:
- Explicit dependencies via function parameters
- Automatic DAG construction
- Zero overhead execution
"""

# Expose feature modules for Hamilton driver
from app.pipeline.hamilton_features import git_features
from app.pipeline.hamilton_features import build_features
from app.pipeline.hamilton_features import github_features
from app.pipeline.hamilton_features import repo_features

__all__ = [
    "git_features",
    "build_features",
    "github_features",
    "repo_features",
]
