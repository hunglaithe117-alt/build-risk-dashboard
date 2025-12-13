"""
Dataset Scan Service

Orchestrates scanning datasets using integration tools (SonarQube, Trivy).
"""

import logging
from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.dataset_scan import DatasetScan, DatasetScanStatus
from app.entities.dataset_scan_result import DatasetScanResult
from app.repositories.dataset_scan import DatasetScanRepository
from app.repositories.dataset_scan_result import DatasetScanResultRepository
from app.repositories.dataset_version import DatasetVersionRepository
from app.integrations import get_tool, get_available_tools, ToolType

logger = logging.getLogger(__name__)


class DatasetScanService:
    """Service for managing dataset scans."""

    def __init__(self, db: Database):
        self.db = db
        self.scan_repo = DatasetScanRepository(db)
        self.result_repo = DatasetScanResultRepository(db)
        self.version_repo = DatasetVersionRepository(db)

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available integration tools with their info."""
        return [tool.to_info_dict() for tool in get_available_tools()]

    def get_unique_commits(
        self, dataset_id: str, version_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get unique commits from a dataset for scan selection UI.

        Returns list of:
        {
            "sha": "abc123...",
            "repo_full_name": "owner/repo",
            "row_count": 5,
            "row_indices": [0, 3, 7, 12, 15],
            "last_scanned": "2024-01-15T...",  # or null if never scanned
            "scan_results": {...}  # summary if previously scanned
        }
        """
        # Get latest version if not specified
        if version_id:
            version = self.version_repo.find_by_id(version_id)
        else:
            version = self.version_repo.find_latest_by_dataset(dataset_id)

        if not version or not version.data:
            return []

        # Build commit map
        commit_map: Dict[str, Dict[str, Any]] = {}

        for idx, row in enumerate(version.data):
            commit_sha = row.get("commit_sha") or row.get("head_sha")
            repo_name = row.get("repo_full_name") or row.get("full_name")

            if not commit_sha or not repo_name:
                continue

            key = f"{repo_name}:{commit_sha}"

            if key not in commit_map:
                commit_map[key] = {
                    "sha": commit_sha,
                    "repo_full_name": repo_name,
                    "row_count": 0,
                    "row_indices": [],
                    "last_scanned": None,
                    "scan_results": None,
                }

            commit_map[key]["row_count"] += 1
            commit_map[key]["row_indices"].append(idx)

        # Look up previous scan results for each commit
        for key, commit_info in commit_map.items():
            results = self.result_repo.find_by_dataset_and_commit(
                dataset_id, commit_info["sha"]
            )
            if results:
                # Get latest completed result
                completed = [r for r in results if r.status == "completed"]
                if completed:
                    latest = max(
                        completed, key=lambda r: r.completed_at or r.created_at
                    )
                    commit_info["last_scanned"] = (
                        latest.completed_at or latest.created_at
                    )
                    commit_info["scan_results"] = latest.results

        return list(commit_map.values())

    def start_scan(
        self,
        dataset_id: str,
        user_id: str,
        tool_type: str,
        selected_commit_shas: Optional[List[str]] = None,
    ) -> DatasetScan:
        """
        Start a scan job for a dataset.

        Args:
            dataset_id: Dataset to scan
            user_id: User initiating the scan
            tool_type: Tool to use (sonarqube or trivy)
            selected_commit_shas: Specific commits to scan (None = all)

        Returns:
            Created DatasetScan entity
        """
        # Validate tool
        tool = get_tool(tool_type)
        if not tool:
            raise ValueError(f"Unknown tool type: {tool_type}")
        if not tool.is_available():
            raise ValueError(f"Tool {tool_type} is not configured or available")

        # Get unique commits
        unique_commits = self.get_unique_commits(dataset_id)
        if not unique_commits:
            raise ValueError("No commits found in dataset")

        # Filter to selected commits if specified
        if selected_commit_shas:
            unique_commits = [
                c for c in unique_commits if c["sha"] in selected_commit_shas
            ]
            if not unique_commits:
                raise ValueError("None of the selected commits found in dataset")

        # Create scan record
        scan = DatasetScan(
            dataset_id=ObjectId(dataset_id),
            user_id=ObjectId(user_id),
            tool_type=tool_type,
            commits=unique_commits,
            selected_commit_shas=selected_commit_shas,
            total_commits=len(unique_commits),
        )
        scan = self.scan_repo.insert_one(scan)

        # Create result records for each commit
        results = []
        for commit in unique_commits:
            result = DatasetScanResult(
                scan_id=scan.id,
                dataset_id=ObjectId(dataset_id),
                commit_sha=commit["sha"],
                repo_full_name=commit["repo_full_name"],
                row_indices=commit["row_indices"],
            )
            results.append(result)

        if results:
            self.result_repo.bulk_insert(results)

        # Dispatch Celery task
        self._dispatch_scan_task(scan)

        return scan

    def _dispatch_scan_task(self, scan: DatasetScan) -> str:
        """Dispatch Celery task for the scan."""
        from app.tasks.integration_scan import run_dataset_scan

        task = run_dataset_scan.delay(str(scan.id))

        # Update scan with task ID
        self.scan_repo.update_one(str(scan.id), {"task_id": task.id})

        return task.id

    def get_scan(self, scan_id: str) -> Optional[DatasetScan]:
        """Get a scan by ID."""
        return self.scan_repo.find_by_id(scan_id)

    def list_scans(
        self, dataset_id: str, skip: int = 0, limit: int = 20
    ) -> tuple[List[DatasetScan], int]:
        """List scans for a dataset with pagination."""
        return self.scan_repo.find_by_dataset(dataset_id, skip=skip, limit=limit)

    def get_active_scans(self, dataset_id: str) -> List[DatasetScan]:
        """Get currently active scans for a dataset."""
        return self.scan_repo.find_active_by_dataset(dataset_id)

    def cancel_scan(self, scan_id: str) -> bool:
        """Cancel a running scan."""
        scan = self.scan_repo.find_by_id(scan_id)
        if not scan:
            return False

        if scan.status not in (
            DatasetScanStatus.PENDING,
            DatasetScanStatus.RUNNING,
            DatasetScanStatus.PARTIAL,
        ):
            return False

        # Revoke Celery task if exists
        if scan.task_id:
            from app.celery_app import celery_app

            celery_app.control.revoke(scan.task_id, terminate=True)

        self.scan_repo.mark_status(scan_id, DatasetScanStatus.CANCELLED)
        return True

    def get_scan_results(
        self, scan_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[List[DatasetScanResult], int]:
        """Get results for a scan with pagination."""
        return self.result_repo.find_by_scan_paginated(scan_id, skip=skip, limit=limit)

    def get_scan_summary(self, scan_id: str) -> Dict[str, Any]:
        """Get aggregated summary of scan results."""
        scan = self.scan_repo.find_by_id(scan_id)
        if not scan:
            return {}

        status_counts = self.result_repo.count_by_scan_status(scan_id)
        aggregated = self.result_repo.get_aggregated_results(scan_id)

        return {
            "scan_id": scan_id,
            "tool_type": scan.tool_type,
            "status": scan.status.value,
            "progress": scan.progress_percentage,
            "total_commits": scan.total_commits,
            "status_counts": status_counts,
            "aggregated_metrics": aggregated,
        }

    def handle_sonar_webhook(
        self, component_key: str, metrics: Dict[str, Any]
    ) -> Optional[DatasetScanResult]:
        """
        Handle SonarQube webhook callback.

        Called when SonarQube finishes analysis and sends webhook.
        Updates the corresponding result and checks if scan is complete.
        """
        result = self.result_repo.find_by_component_key(component_key)
        if not result:
            logger.warning(
                f"No pending result found for component_key: {component_key}"
            )
            return None

        # Update result with metrics
        self.result_repo.mark_completed(str(result.id), metrics)

        # Check if all results for this scan are done
        self._check_scan_completion(str(result.scan_id))

        return result

    def _check_scan_completion(self, scan_id: str) -> None:
        """Check if a scan is complete and update status."""
        pending = self.result_repo.find_pending_by_scan(scan_id)

        if not pending:
            # All done
            status_counts = self.result_repo.count_by_scan_status(scan_id)
            aggregated = self.result_repo.get_aggregated_results(scan_id)

            self.scan_repo.mark_status(
                scan_id,
                DatasetScanStatus.COMPLETED,
                results_summary=aggregated,
            )
            self.scan_repo.update_progress(
                scan_id,
                scanned=status_counts.get("completed", 0),
                failed=status_counts.get("failed", 0),
                pending=0,
            )
        else:
            # Still pending
            status_counts = self.result_repo.count_by_scan_status(scan_id)
            self.scan_repo.update_progress(
                scan_id,
                scanned=status_counts.get("completed", 0),
                failed=status_counts.get("failed", 0),
                pending=len(pending),
            )
