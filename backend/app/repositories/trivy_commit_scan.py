"""
TrivyCommitScan Repository.
"""

from datetime import datetime, timezone
from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.trivy_commit_scan import TrivyCommitScan, TrivyScanStatus
from app.repositories.base import BaseRepository


class TrivyCommitScanRepository(BaseRepository[TrivyCommitScan]):
    """Repository for TrivyCommitScan entities."""

    def __init__(self, db: Database):
        super().__init__(db, "trivy_commit_scans", TrivyCommitScan)

    def mark_scanning(self, scan_id: ObjectId) -> None:
        """Mark scan as in progress."""
        self.collection.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "status": TrivyScanStatus.SCANNING.value,
                    "started_at": datetime.now(timezone.utc),
                }
            },
        )

    def mark_completed(
        self,
        scan_id: ObjectId,
        metrics: dict,
        builds_affected: int,
    ) -> None:
        """Mark scan as completed with results."""
        self.collection.update_one(
            {"_id": scan_id},
            {
                "$set": {
                    "status": TrivyScanStatus.COMPLETED.value,
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
                    "status": TrivyScanStatus.FAILED.value,
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
                    "status": TrivyScanStatus.PENDING.value,
                    "error_message": None,
                    "started_at": None,
                    "completed_at": None,
                },
            },
        )

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
        status: Optional[TrivyScanStatus] = None,
    ) -> tuple[List[TrivyCommitScan], int]:
        """List scans for a scenario with pagination. Returns (items, total)."""
        query = {"scenario_id": scenario_id}
        if status:
            query["status"] = status.value
        total = self.collection.count_documents(query)
        items = list(
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )
        return [TrivyCommitScan(**doc) for doc in items], total

    def count_by_scenario(self, scenario_id: ObjectId) -> int:
        """Count all scans for a scenario."""
        return self.collection.count_documents({"scenario_id": scenario_id})

    def count_by_scenario_and_status(
        self, scenario_id: ObjectId, status: TrivyScanStatus
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
    ) -> Optional[TrivyCommitScan]:
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
        scan_config: Optional[dict] = None,
        selected_metrics: Optional[list] = None,
    ) -> TrivyCommitScan:
        """Create new scan record for scenario or return existing."""
        existing = self.find_by_scenario_and_commit(scenario_id, commit_sha)
        if existing:
            return existing

        scan = TrivyCommitScan(
            scenario_id=scenario_id,
            commit_sha=commit_sha,
            repo_full_name=repo_full_name,
            raw_repo_id=raw_repo_id,
            scan_config=scan_config,
            selected_metrics=selected_metrics,
            status=TrivyScanStatus.PENDING,
        )
        return self.insert_one(scan)

    def get_failed_by_scenario(self, scenario_id: ObjectId) -> List[TrivyCommitScan]:
        """Get all failed scans for a scenario."""
        return self.find_many(
            {
                "scenario_id": scenario_id,
                "status": TrivyScanStatus.FAILED.value,
            }
        )

    def delete_by_scenario(self, scenario_id: ObjectId | str, session=None) -> int:
        """Delete all scans for a scenario."""
        if isinstance(scenario_id, str):
            scenario_id = ObjectId(scenario_id)
        return self.delete_many({"scenario_id": scenario_id}, session=session)
