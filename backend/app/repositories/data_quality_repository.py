"""
Data Quality Repository - Database operations for quality evaluation reports.
"""

from typing import List, Optional

from bson import ObjectId

from app.entities.data_quality import DataQualityReport

from .base import BaseRepository


class DataQualityRepository(BaseRepository[DataQualityReport]):
    """Repository for data quality reports."""

    def __init__(self, db):
        super().__init__(db, "data_quality_reports", DataQualityReport)

    def find_by_scenario(self, scenario_id: str) -> Optional[DataQualityReport]:
        """
        Get the latest quality report for a scenario.

        Args:
            scenario_id: Scenario ID

        Returns:
            Latest DataQualityReport or None
        """
        return self.find_one(
            {"scenario_id": self._to_object_id(scenario_id)},
        )

    def delete_by_scenario(self, scenario_id: str, session=None) -> int:
        """
        Delete all reports for a scenario (cleanup).

        Args:
            scenario_id: Scenario ID
            session: Optional MongoDB session for transactions

        Returns:
            Number of deleted documents
        """
        result = self.collection.delete_many(
            {"scenario_id": ObjectId(scenario_id)},
            session=session,
        )
        return result.deleted_count

    def find_pending_or_running(self, scenario_id: str) -> Optional[DataQualityReport]:
        """
        Find any pending or running evaluation for a scenario.

        Args:
            scenario_id: Scenario ID

        Returns:
            DataQualityReport if found, None otherwise
        """
        return self.find_one(
            {
                "scenario_id": self._to_object_id(scenario_id),
                "status": {"$in": ["pending", "running"]},
            }
        )
