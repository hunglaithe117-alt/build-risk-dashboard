"""Repository for EnrichmentRepository entities (enrichment_repositories collection)."""

from typing import List, Optional
from datetime import datetime

from bson import ObjectId
from pymongo.database import Database

from app.repositories.base import BaseRepository
from app.entities import EnrichmentRepository, RepoValidationStatus, CIProvider
from app.utils.datetime import utc_now


class EnrichmentRepoRepository(BaseRepository[EnrichmentRepository]):
    """Repository for enrichment_repositories collection."""

    def __init__(self, db: Database):
        super().__init__(db, "enrichment_repositories", EnrichmentRepository)

    def find_by_dataset(
        self, dataset_id: str | ObjectId, skip: int = 0, limit: int = 0
    ) -> List[EnrichmentRepository]:
        """Find all repos for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return []
        return self.find_many(
            {"dataset_id": oid},
            sort=[("full_name", 1)],
            skip=skip,
            limit=limit,
        )

    def find_by_dataset_and_name(
        self, dataset_id: str | ObjectId, full_name: str
    ) -> Optional[EnrichmentRepository]:
        """Find a repo by dataset and full name."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return None
        return self.find_one({"dataset_id": oid, "full_name": full_name})

    def upsert_repo(
        self,
        dataset_id: str | ObjectId,
        full_name: str,
        ci_provider: str,
        source_languages: List[str],
        test_frameworks: List[str],
        validation_status: RepoValidationStatus = RepoValidationStatus.VALID,
    ) -> EnrichmentRepository:
        """Insert or update a repository config."""
        oid = self._to_object_id(dataset_id)
        existing = self.find_by_dataset_and_name(dataset_id, full_name)

        now = utc_now()

        if existing:
            # Update existing
            self.update_one(
                existing.id,
                {
                    "ci_provider": ci_provider,
                    "source_languages": source_languages,
                    "test_frameworks": test_frameworks,
                    "validation_status": validation_status.value,
                    "validated_at": now,
                },
            )
            return self.find_by_id(existing.id)
        else:
            # Insert new
            repo = EnrichmentRepository(
                dataset_id=oid,
                full_name=full_name,
                ci_provider=CIProvider(ci_provider),
                source_languages=source_languages,
                test_frameworks=test_frameworks,
                validation_status=validation_status,
                validated_at=now,
            )
            return self.insert_one(repo)

    def delete_by_dataset(self, dataset_id: str | ObjectId) -> int:
        """Delete all repos for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return 0
        return self.delete_many({"dataset_id": oid})

    def count_by_dataset(self, dataset_id: str | ObjectId) -> int:
        """Count repos for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return 0
        return self.count({"dataset_id": oid})

    def update_repo_config(
        self,
        dataset_id: str | ObjectId,
        full_name: str,
        ci_provider: str,
        source_languages: List[str],
        test_frameworks: List[str],
    ) -> bool:
        """Update repo config by dataset and name. Returns True if updated."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return False
        result = self.collection.update_one(
            {"dataset_id": oid, "full_name": full_name},
            {
                "$set": {
                    "ci_provider": ci_provider,
                    "source_languages": source_languages,
                    "test_frameworks": test_frameworks,
                }
            },
        )
        return result.modified_count > 0
