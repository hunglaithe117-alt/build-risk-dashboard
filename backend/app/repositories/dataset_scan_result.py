"""Repository for DatasetScanResult entity."""

from typing import List, Optional, Dict, Any

from bson import ObjectId
from pymongo.database import Database

from app.entities.dataset_scan_result import DatasetScanResult
from .base import BaseRepository


class DatasetScanResultRepository(BaseRepository[DatasetScanResult]):
    """Repository for DatasetScanResult entities."""

    def __init__(self, db: Database):
        super().__init__(db, "dataset_scan_results", DatasetScanResult)

    def find_by_scan(self, scan_id: str) -> List[DatasetScanResult]:
        """Find all results for a scan."""
        return self.find_many(
            {"scan_id": self._to_object_id(scan_id)},
            sort=[("created_at", 1)],
        )

    def find_by_scan_paginated(
        self, scan_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[List[DatasetScanResult], int]:
        """Find results for a scan with pagination."""
        return self.paginate(
            {"scan_id": self._to_object_id(scan_id)},
            sort=[("created_at", 1)],
            skip=skip,
            limit=limit,
        )

    def find_by_component_key(self, component_key: str) -> Optional[DatasetScanResult]:
        """Find a result by its SonarQube component key (for webhook matching)."""
        return self.find_one({"component_key": component_key})

    def find_pending_by_scan(self, scan_id: str) -> List[DatasetScanResult]:
        """Find pending results for a scan (for async tool tracking)."""
        return self.find_many(
            {
                "scan_id": self._to_object_id(scan_id),
                "status": {"$in": ["pending", "scanning"]},
            }
        )

    def find_by_dataset_and_commit(
        self, dataset_id: str, commit_sha: str
    ) -> List[DatasetScanResult]:
        """Find results for a specific commit across all scans for a dataset."""
        return self.find_many(
            {
                "dataset_id": self._to_object_id(dataset_id),
                "commit_sha": commit_sha,
            }
        )

    def mark_scanning(
        self, result_id: str, component_key: Optional[str] = None
    ) -> bool:
        """Mark a result as currently scanning."""
        from datetime import datetime, timezone

        update: dict = {
            "status": "scanning",
            "started_at": datetime.now(timezone.utc),
        }
        if component_key:
            update["component_key"] = component_key

        result = self.collection.update_one(
            {"_id": self._to_object_id(result_id)},
            {"$set": update},
        )
        return result.modified_count > 0

    def mark_completed(
        self,
        result_id: str,
        results: Dict[str, Any],
        duration_ms: Optional[int] = None,
    ) -> bool:
        """Mark a result as completed with scan data."""
        from datetime import datetime, timezone

        update: dict = {
            "status": "completed",
            "results": results,
            "completed_at": datetime.now(timezone.utc),
        }
        if duration_ms:
            update["scan_duration_ms"] = duration_ms

        result = self.collection.update_one(
            {"_id": self._to_object_id(result_id)},
            {"$set": update},
        )
        return result.modified_count > 0

    def mark_failed(self, result_id: str, error: str) -> bool:
        """Mark a result as failed."""
        from datetime import datetime, timezone

        result = self.collection.update_one(
            {"_id": self._to_object_id(result_id)},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error,
                    "completed_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    def count_by_scan_status(self, scan_id: str) -> Dict[str, int]:
        """Count results by status for a scan."""
        pipeline = [
            {"$match": {"scan_id": self._to_object_id(scan_id)}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        result = list(self.collection.aggregate(pipeline))
        return {r["_id"]: r["count"] for r in result}

    def bulk_insert(self, results: List[DatasetScanResult]) -> List[str]:
        """Insert multiple results at once."""
        if not results:
            return []

        docs = [r.to_mongo() for r in results]
        result = self.collection.insert_many(docs)
        return [str(id) for id in result.inserted_ids]

    def get_aggregated_results(self, scan_id: str) -> Dict[str, Any]:
        """Get aggregated metrics across all results for a scan."""
        pipeline = [
            {
                "$match": {
                    "scan_id": self._to_object_id(scan_id),
                    "status": "completed",
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_results": {"$sum": 1},
                    # Sum up common vulnerability counts
                    "total_vuln_critical": {
                        "$sum": {"$ifNull": ["$results.vuln_critical", 0]}
                    },
                    "total_vuln_high": {"$sum": {"$ifNull": ["$results.vuln_high", 0]}},
                    "total_vuln_medium": {
                        "$sum": {"$ifNull": ["$results.vuln_medium", 0]}
                    },
                    "total_vuln_low": {"$sum": {"$ifNull": ["$results.vuln_low", 0]}},
                    # For SonarQube
                    "total_bugs": {"$sum": {"$ifNull": ["$results.bugs", 0]}},
                    "total_vulnerabilities": {
                        "$sum": {"$ifNull": ["$results.vulnerabilities", 0]}
                    },
                    "total_code_smells": {
                        "$sum": {"$ifNull": ["$results.code_smells", 0]}
                    },
                }
            },
        ]
        result = list(self.collection.aggregate(pipeline))
        return result[0] if result else {}
