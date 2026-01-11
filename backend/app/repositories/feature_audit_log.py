from typing import Optional

from app.entities.feature_audit_log import AuditLogCategory, FeatureAuditLog

from .base import BaseRepository


class FeatureAuditLogRepository(BaseRepository[FeatureAuditLog]):
    """Repository for FeatureAuditLog entities."""

    def __init__(self, db):
        super().__init__(db, "feature_audit_logs", FeatureAuditLog)

    def delete_by_raw_repo_id(
        self, raw_repo_id, category: AuditLogCategory, session=None
    ) -> int:
        result = self.collection.delete_many(
            {
                "raw_repo_id": self._to_object_id(raw_repo_id),
                "category": category.value,
            },
            session=session,
        )
        return result.deleted_count

    def delete_by_version_id(self, version_id: str, session=None) -> int:
        """Delete all audit logs for a specific version (scenario)."""
        result = self.collection.delete_many(
            {"scenario_id": self._to_object_id(version_id)},
            session=session,
        )
        return result.deleted_count

    def find_by_enrichment_build(
        self,
        enrichment_build_id: str,
    ) -> Optional[FeatureAuditLog]:
        """
        Find audit log for a specific enrichment build.

        Args:
            enrichment_build_id: The DatasetEnrichmentBuild ID

        Returns:
            FeatureAuditLog or None if not found
        """
        return self.find_one(
            {"enrichment_build_id": self._to_object_id(enrichment_build_id)}
        )
