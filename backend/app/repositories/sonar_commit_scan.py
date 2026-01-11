"""
SonarCommitScan Repository - CRUD operations for SonarQube commit scans.
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.sonar_commit_scan import SonarCommitScan, SonarScanStatus
from app.repositories.base import BaseRepository


class SonarCommitScanRepository(BaseRepository[SonarCommitScan]):
    """Repository for SonarCommitScan entities."""

    def __init__(self, db: Database):
        super().__init__(db, "sonar_commit_scans", SonarCommitScan)

    def find_by_component_key(self, component_key: str) -> Optional[SonarCommitScan]:
        """Find scan by component key."""
        return self.find_one({"component_key": component_key})

    def find_pending_by_component_key(
        self,
        component_key: str,
    ) -> Optional[SonarCommitScan]:
        """Find only scanning (not completed) record by component key."""
        return self.find_one(
            {
                "component_key": component_key,
                "status": {
                    "$in": [
                        SonarScanStatus.PENDING.value,
                        SonarScanStatus.SCANNING.value,
                    ]
                },
            }
        )

    def mark_scanning(self, scan_id: ObjectId) -> None:
        """Mark scan as in progress."""
        self.collection.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "status": SonarScanStatus.SCANNING.value,
                    "started_at": datetime.now(timezone.utc),
                }
            },
        )

    def mark_completed(
        self,
        scan_id: ObjectId,
        metrics: dict,
        builds_affected: int = 0,
    ) -> None:
        """Mark scan as completed with metrics."""
        self.collection.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "status": SonarScanStatus.COMPLETED.value,
                    "metrics": metrics,
                    "builds_affected": builds_affected,
                    "completed_at": datetime.now(timezone.utc),
                    "error_message": None,
                }
            },
        )

    def mark_failed(self, scan_id: ObjectId, error_message: str) -> None:
        """Mark scan as failed."""
        self.collection.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "status": SonarScanStatus.FAILED.value,
                    "error_message": error_message,
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )

    def increment_retry(self, scan_id: ObjectId) -> None:
        """Increment retry count and reset to pending."""
        self.collection.update_one(
            {"_id": scan_id},
            {
                "$inc": {"retry_count": 1},
                "$set": {
                    "status": SonarScanStatus.PENDING.value,
                    "error_message": None,
                    "started_at": None,
                    "completed_at": None,
                },
            },
        )

    def delete_old_scans(self, days: int = 30) -> int:
        """Delete completed scans older than specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        result = self.collection.delete_many(
            {
                "status": {
                    "$in": [
                        SonarScanStatus.COMPLETED.value,
                        SonarScanStatus.FAILED.value,
                    ]
                },
                "completed_at": {"$lt": cutoff},
            }
        )
        return result.deleted_count

    def delete_by_version(self, version_id: ObjectId | str, session=None) -> int:
        """Delete all scans for a version (legacy cleanup)."""
        if isinstance(version_id, str):
            version_id = ObjectId(version_id)
        return self.delete_many({"dataset_version_id": version_id}, session=session)

    # ========================================================================
    # Scenario-based methods (Training Scenario flow)
    # ========================================================================

    def list_by_scenario(
        self,
        scenario_id: ObjectId,
        skip: int = 0,
        limit: int = 10,
        status: Optional[SonarScanStatus] = None,
    ) -> tuple[List[SonarCommitScan], int]:
        """List scans for a scenario with pagination. Returns (items, total)."""
        query = {"scenario_id": scenario_id}
        if status:
            query["status"] = status.value
        total = self.collection.count_documents(query)
        items = list(
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )
        return [SonarCommitScan(**doc) for doc in items], total

    def count_by_scenario(self, scenario_id: ObjectId) -> int:
        """Count all scans for a scenario."""
        return self.collection.count_documents({"scenario_id": scenario_id})

    def count_by_scenario_and_status(
        self, scenario_id: ObjectId, status: SonarScanStatus
    ) -> int:
        """Count scans for a scenario filtered by status."""
        return self.collection.count_documents(
            {
                "scenario_id": scenario_id,
                "status": status.value,
            }
        )

    def find_by_scenario_and_commit(
        self,
        scenario_id: ObjectId,
        commit_sha: str,
    ) -> Optional[SonarCommitScan]:
        """Find scan for specific scenario + commit."""
        return self.find_one(
            {
                "scenario_id": scenario_id,
                "commit_sha": commit_sha,
            }
        )

    def create_or_get_for_scenario(
        self,
        scenario_id: ObjectId,
        commit_sha: str,
        repo_full_name: str,
        raw_repo_id: ObjectId,
        component_key: str,
        scan_config: Optional[dict] = None,
        selected_metrics: Optional[list] = None,
    ) -> SonarCommitScan:
        """Create new scan record for scenario or return existing."""
        existing = self.find_by_scenario_and_commit(scenario_id, commit_sha)
        if existing:
            return existing

        scan = SonarCommitScan(
            scenario_id=scenario_id,
            commit_sha=commit_sha,
            repo_full_name=repo_full_name,
            raw_repo_id=raw_repo_id,
            component_key=component_key,
            scan_config=scan_config,
            selected_metrics=selected_metrics,
            status=SonarScanStatus.PENDING,
        )
        return self.insert_one(scan)

    def get_failed_by_scenario(self, scenario_id: ObjectId) -> List[SonarCommitScan]:
        """Get all failed scans for a scenario."""
        return self.find_many(
            {
                "scenario_id": scenario_id,
                "status": SonarScanStatus.FAILED.value,
            }
        )

    def delete_by_scenario(self, scenario_id: ObjectId | str, session=None) -> int:
        """Delete all scans for a scenario."""
        if isinstance(scenario_id, str):
            scenario_id = ObjectId(scenario_id)
        return self.delete_many({"scenario_id": scenario_id}, session=session)
