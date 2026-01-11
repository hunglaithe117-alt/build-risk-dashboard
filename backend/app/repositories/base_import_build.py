"""
Base Import Build Repository - Protocol and Factory for Model/Dataset pipelines.

This module provides:
- Protocol class defining common interface for progressive resource updates
- Wrapper classes adapting each repository to the common interface
- Factory function to get the appropriate wrapper based on pipeline type

Usage:
    updater = get_progressive_updater(db, "model", pipeline_id=repo_config_id)
    updater.update_resource_batch("git_history", ResourceStatus.COMPLETED)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional, Protocol

if TYPE_CHECKING:
    from pymongo.database import Database

    from app.entities.model_import_build import ResourceStatus


class ProgressiveUpdaterProtocol(Protocol):
    """Protocol for progressive resource status updates.

    Both Model and Dataset pipelines implement this interface
    to allow shared ingestion tasks to update resource status.
    """

    def update_resource_batch(
        self,
        resource: str,
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        """Update resource status for all INGESTING builds in scope.

        Args:
            resource: Resource name (git_history, git_worktree, build_logs)
            status: New status
            error: Optional error message

        Returns:
            Number of builds updated
        """
        ...

    def update_resource_by_commits(
        self,
        resource: str,
        commits: List[str],
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        """Update resource status for builds matching specific commits.

        Args:
            resource: Resource name (typically git_worktree)
            commits: List of commit SHAs
            status: New status
            error: Optional error message

        Returns:
            Number of builds updated
        """
        ...

    def update_resource_by_ci_run_ids(
        self,
        resource: str,
        ci_run_ids: List[str],
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        """Update resource status for builds matching specific CI run IDs.

        Args:
            resource: Resource name (typically build_logs)
            ci_run_ids: List of CI run IDs
            status: New status
            error: Optional error message

        Returns:
            Number of builds updated
        """
        ...


class ModelImportBuildUpdater:
    """Wrapper for ModelImportBuildRepository implementing ProgressiveUpdaterProtocol."""

    def __init__(self, db: "Database", config_id: str):
        from app.repositories.model_import_build import ModelImportBuildRepository

        self.repo = ModelImportBuildRepository(db)
        self.config_id = config_id

    def update_resource_batch(
        self,
        resource: str,
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        return self.repo.update_resource_status_batch(
            config_id=self.config_id,
            resource=resource,
            status=status,
            error=error,
        )

    def update_resource_by_commits(
        self,
        resource: str,
        commits: List[str],
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        return self.repo.update_resource_by_commits(
            config_id=self.config_id,
            resource=resource,
            commits=commits,
            status=status,
            error=error,
        )

    def update_resource_by_ci_run_ids(
        self,
        resource: str,
        ci_run_ids: List[str],
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        return self.repo.update_resource_by_ci_run_ids(
            config_id=self.config_id,
            resource=resource,
            ci_run_ids=ci_run_ids,
            status=status,
            error=error,
        )


class DatasetImportBuildUpdater:
    """Wrapper for TrainingIngestionBuildRepository implementing ProgressiveUpdaterProtocol.

    Adapts the new TrainingIngestionBuild flow (scenario_id) to the progressive updater interface.
    """

    def __init__(self, db: "Database", version_id: str, raw_repo_id: str):
        # version_id here corresponds to scenario_id in the new flow
        from app.repositories.training_ingestion_build import (
            TrainingIngestionBuildRepository,
        )

        self.repo = TrainingIngestionBuildRepository(db)
        self.scenario_id = version_id
        self.raw_repo_id = raw_repo_id

    def update_resource_batch(
        self,
        resource: str,
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        return self.repo.update_resource_batch(
            scenario_id=self.scenario_id,
            raw_repo_id=self.raw_repo_id,
            resource=resource,
            status=status,
            error=error,
        )

    def update_resource_by_commits(
        self,
        resource: str,
        commits: List[str],
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        return self.repo.update_resource_by_commits(
            scenario_id=self.scenario_id,
            raw_repo_id=self.raw_repo_id,
            resource=resource,
            commits=commits,
            status=status,
            error=error,
        )

    def update_resource_by_ci_run_ids(
        self,
        resource: str,
        ci_run_ids: List[str],
        status: "ResourceStatus",
        error: Optional[str] = None,
    ) -> int:
        return self.repo.update_resource_by_ci_run_ids(
            scenario_id=self.scenario_id,
            raw_repo_id=self.raw_repo_id,
            resource=resource,
            ci_run_ids=ci_run_ids,
            status=status,
            error=error,
        )


def get_progressive_updater(
    db: "Database",
    pipeline_type: str,
    pipeline_id: str,
    raw_repo_id: str = "",
) -> ProgressiveUpdaterProtocol:
    """Factory function to get the appropriate progressive updater.

    Args:
        db: MongoDB database instance
        pipeline_type: "model" or "dataset"
        pipeline_id: ModelRepoConfig ID (model) or DatasetVersion ID (dataset)
        raw_repo_id: Required for dataset pipeline (multi-repo support)

    Returns:
        Object implementing ProgressiveUpdaterProtocol

    Raises:
        ValueError: If pipeline_type is unknown or raw_repo_id missing for dataset
    """
    if pipeline_type == "model":
        return ModelImportBuildUpdater(db, pipeline_id)
    elif pipeline_type == "dataset":
        if not raw_repo_id:
            raise ValueError("raw_repo_id is required for dataset pipeline")
        return DatasetImportBuildUpdater(db, pipeline_id, raw_repo_id)
    else:
        raise ValueError(f"Unknown pipeline_type: {pipeline_type}")
