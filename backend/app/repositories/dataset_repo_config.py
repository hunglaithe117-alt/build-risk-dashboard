"""Repository for DatasetRepoConfig entities (repo config for dataset enrichment)."""

from datetime import datetime
from typing import List, Optional

from bson import ObjectId

from app.entities.dataset_repo_config import DatasetRepoConfig
from app.entities.enums import DatasetRepoValidationStatus
from app.repositories.base import BaseRepository


class DatasetRepoConfigRepository(BaseRepository[DatasetRepoConfig]):
    """Repository for DatasetRepoConfig entities (Dataset enrichment flow)."""

    def __init__(self, db) -> None:
        super().__init__(db, "dataset_repo_configs", DatasetRepoConfig)

    def find_by_dataset_and_repo(
        self,
        dataset_id: ObjectId,
        raw_repo_id: ObjectId,
    ) -> Optional[DatasetRepoConfig]:
        """Find config by dataset and raw repository."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "raw_repo_id": raw_repo_id,
            }
        )
        return DatasetRepoConfig(**doc) if doc else None

    def find_by_dataset_and_csv_name(
        self,
        dataset_id: ObjectId,
        repo_name_from_csv: str,
    ) -> Optional[DatasetRepoConfig]:
        """Find config by dataset and original CSV repo name."""
        doc = self.collection.find_one(
            {
                "dataset_id": dataset_id,
                "repo_name_from_csv": repo_name_from_csv,
            }
        )
        return DatasetRepoConfig(**doc) if doc else None

    def list_by_dataset(
        self,
        dataset_id: ObjectId,
        skip: int = 0,
        limit: int = 100,
        status: Optional[DatasetRepoValidationStatus] = None,
    ) -> tuple[List[DatasetRepoConfig], int]:
        """List all repo configs for a dataset with pagination."""
        query: dict = {"dataset_id": dataset_id}
        if status:
            status_value = status.value if hasattr(status, "value") else status
            query["validation_status"] = status_value

        total = self.collection.count_documents(query)
        cursor = (
            self.collection.find(query).sort("created_at", -1).skip(skip).limit(limit)
        )
        items = [DatasetRepoConfig(**doc) for doc in cursor]
        return items, total

    def update_validation_status(
        self,
        config_id: ObjectId,
        status: DatasetRepoValidationStatus,
        raw_repo_id: Optional[ObjectId] = None,
        normalized_full_name: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update validation status for a config."""
        update = {
            "validation_status": status.value if hasattr(status, "value") else status,
            "validated_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        if raw_repo_id:
            update["raw_repo_id"] = raw_repo_id
        if normalized_full_name:
            update["normalized_full_name"] = normalized_full_name
        if error:
            update["validation_error"] = error

        self.collection.update_one({"_id": config_id}, {"$set": update})

    def increment_builds_found(
        self,
        config_id: ObjectId,
        found: int = 0,
        not_found: int = 0,
    ) -> None:
        """Increment build counts for a config."""
        inc = {}
        if found:
            inc["builds_found"] = found
        if not_found:
            inc["builds_not_found"] = not_found

        if inc:
            self.collection.update_one(
                {"_id": config_id},
                {
                    "$inc": inc,
                    "$set": {"updated_at": datetime.utcnow()},
                },
            )

    def increment_builds_processed(
        self,
        config_id: ObjectId,
        count: int = 1,
    ) -> None:
        """Increment the builds processed count."""
        self.collection.update_one(
            {"_id": config_id},
            {
                "$inc": {"builds_processed": count},
                "$set": {"updated_at": datetime.utcnow()},
            },
        )

    def count_by_dataset(
        self,
        dataset_id: ObjectId,
        status: Optional[DatasetRepoValidationStatus] = None,
    ) -> int:
        """Count repo configs for a dataset, optionally filtered by status."""
        query: dict = {"dataset_id": dataset_id}
        if status:
            status_value = status.value if hasattr(status, "value") else status
            query["validation_status"] = status_value
        return self.collection.count_documents(query)

    def delete_by_dataset(self, dataset_id: str) -> int:
        """Delete all repo configs for a dataset."""
        oid = self._to_object_id(dataset_id)
        if not oid:
            return 0
        result = self.collection.delete_many({"dataset_id": oid})
        return result.deleted_count

    def find_by_dataset(self, dataset_id: str) -> List[DatasetRepoConfig]:
        """Return all repo configs for a dataset (no pagination)."""
        ds_id = ObjectId(dataset_id)
        cursor = self.collection.find({"dataset_id": ds_id}).sort("created_at", -1)
        return [DatasetRepoConfig(**doc) for doc in cursor]

    def upsert_repo(
        self,
        dataset_id: str,
        full_name: str,
        ci_provider,
        source_languages: list,
        test_frameworks: list,
        validation_status: DatasetRepoValidationStatus,
        raw_repo_id: ObjectId | None = None,
        default_branch: str | None = None,
        is_private: bool | None = None,
    ) -> DatasetRepoConfig:
        """Upsert a dataset repo config by dataset + normalized_full_name.

        Maps the provided `full_name` to both `repo_name_from_csv` and
        `normalized_full_name` for Step 2 where user inputs repos directly.
        Links to `raw_repo_id` when available.
        """
        ds_id = ObjectId(dataset_id)

        update_fields = {
            "repo_name_from_csv": full_name,
            "normalized_full_name": full_name,
            "ci_provider": ci_provider,
            "source_languages": source_languages or [],
            "test_frameworks": test_frameworks or [],
            "validation_status": validation_status.value,
            "updated_at": datetime.utcnow(),
        }

        if raw_repo_id:
            update_fields["raw_repo_id"] = raw_repo_id
        if default_branch is not None:
            update_fields["default_branch"] = default_branch
        if is_private is not None:
            update_fields["is_private"] = is_private

        self.collection.update_one(
            {
                "dataset_id": ds_id,
                "normalized_full_name": full_name,
            },
            {
                "$set": update_fields,
                "$setOnInsert": {
                    "dataset_id": ds_id,
                    "created_at": datetime.utcnow(),
                    "builds_in_csv": 0,
                    "builds_found": 0,
                    "builds_not_found": 0,
                    "builds_processed": 0,
                },
            },
            upsert=True,
        )

        doc = self.collection.find_one(
            {"dataset_id": ds_id, "normalized_full_name": full_name}
        )
        return DatasetRepoConfig(**doc)

    def update_repo_config(
        self,
        dataset_id: str,
        full_name: str,
        ci_provider=None,
        source_languages: list | None = None,
        test_frameworks: list | None = None,
    ) -> bool:
        """Update an existing repo config by dataset + full_name.

        Returns True if updated, False if not found.
        """
        ds_id = ObjectId(dataset_id)

        update_fields: dict = {"updated_at": datetime.utcnow()}
        if ci_provider is not None:
            update_fields["ci_provider"] = ci_provider
        if source_languages is not None:
            update_fields["source_languages"] = source_languages
        if test_frameworks is not None:
            update_fields["test_frameworks"] = test_frameworks

        result = self.collection.update_one(
            {"dataset_id": ds_id, "normalized_full_name": full_name},
            {"$set": update_fields},
        )
        return result.modified_count > 0
