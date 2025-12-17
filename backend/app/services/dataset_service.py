import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence
from uuid import uuid4

import pandas as pd

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import (
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdateRequest,
)
from app.dtos.dataset_repo import DatasetRepoListResponse, DatasetRepoSummary
from app.entities.dataset import DatasetProject, DatasetMapping, DatasetStats
from app.repositories.dataset_repository import DatasetRepository
from app.repositories.dataset_repo_config_repository import DatasetRepoConfigRepository

logger = logging.getLogger(__name__)
DATASET_DIR = Path("../repo-data/datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)
REQUIRED_MAPPING_FIELDS = ["build_id", "repo_name"]


class DatasetService:
    def __init__(self, db: Database):
        self.db = db
        self.repo = DatasetRepository(db)
        self.repo_config_repo = DatasetRepoConfigRepository(db)

    def _serialize(self, dataset) -> DatasetResponse:
        payload = (
            dataset.model_dump(by_alias=True)
            if hasattr(dataset, "model_dump")
            else dataset
        )
        return DatasetResponse.model_validate(payload)

    def _validate_required_mapping(
        self, mapping: Dict[str, Optional[str]], columns: Sequence[str]
    ) -> None:
        """Ensure required fields are mapped to existing columns."""
        missing = []
        for field in REQUIRED_MAPPING_FIELDS:
            column = mapping.get(field)
            if not column or column not in columns:
                missing.append(field)
        if missing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "message": "Required mapping fields are missing or invalid",
                    "missing": missing,
                },
            )

    def list_datasets(
        self, user_id: str, skip: int = 0, limit: int = 20, q: Optional[str] = None
    ) -> DatasetListResponse:
        """List datasets for the current user."""
        datasets, total = self.repo.list_by_user(user_id, skip=skip, limit=limit, q=q)
        return DatasetListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=[self._serialize(ds) for ds in datasets],
        )

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetResponse:
        dataset = self.repo.find_by_id(dataset_id)
        if not dataset or (dataset.user_id and str(dataset.user_id) != user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found"
            )
        return self._serialize(dataset)

    def list_repos(self, dataset_id: str, user_id: str) -> DatasetRepoListResponse:
        """
        List repos for a dataset.

        Uses DatasetRepoConfigRepository to get repos, converts to DTOs.
        """
        dataset = self.repo.find_by_id(dataset_id)
        if not dataset or (dataset.user_id and str(dataset.user_id) != user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found"
            )

        configs = self.repo_config_repo.list_by_dataset(ObjectId(dataset_id))

        items = []
        for c in configs:
            items.append(
                DatasetRepoSummary(
                    _id=c.id,
                    raw_repo_id=c.raw_repo_id,
                    repo_name=c.normalized_full_name,
                    repo_name_from_csv=c.repo_name_from_csv,
                    validation_status=(
                        c.validation_status.value
                        if hasattr(c.validation_status, "value")
                        else c.validation_status
                    ),
                    validation_error=c.validation_error,
                    builds_in_csv=c.builds_in_csv,
                    builds_found=c.builds_found,
                    builds_processed=c.builds_processed,
                )
            )

        return DatasetRepoListResponse(items=items, total=len(items))

    def create_dataset(
        self, user_id: str, payload: DatasetCreateRequest
    ) -> DatasetResponse:
        now = datetime.now(timezone.utc)
        data = payload.model_dump(exclude_none=True)
        data["user_id"] = ObjectId(user_id) if user_id else None
        data["created_at"] = now
        data["updated_at"] = now
        if data.get("mapped_fields") and data.get("columns"):
            self._validate_required_mapping(data["mapped_fields"], data["columns"])
        dataset = self.repo.insert_one(data)
        return self._serialize(dataset)

    def update_dataset(
        self, dataset_id: str, user_id: str, payload: DatasetUpdateRequest
    ) -> DatasetResponse:
        dataset = self.repo.find_by_id(dataset_id)
        if not dataset or (dataset.user_id and str(dataset.user_id) != user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found"
            )

        payload_dict = payload.model_dump(exclude_none=True)
        updates = {}

        if "name" in payload_dict:
            updates["name"] = payload_dict["name"]
        if "description" in payload_dict:
            updates["description"] = payload_dict["description"]
        if "setup_step" in payload_dict:
            updates["setup_step"] = payload_dict["setup_step"]
        if "source_languages" in payload_dict:
            updates["source_languages"] = payload_dict["source_languages"]
        if "test_frameworks" in payload_dict:
            updates["test_frameworks"] = payload_dict["test_frameworks"]

        if "mapped_fields" in payload_dict:
            merged = {}
            if getattr(dataset, "mapped_fields", None):
                merged.update(dataset.mapped_fields.model_dump())
            merged.update(payload_dict["mapped_fields"])
            updates["mapped_fields"] = merged
            self._validate_required_mapping(updates["mapped_fields"], dataset.columns)

        if "stats" in payload_dict:
            merged_stats = {}
            if getattr(dataset, "stats", None):
                merged_stats.update(dataset.stats.model_dump())
            merged_stats.update(payload_dict["stats"])
            updates["stats"] = merged_stats

        if not updates:
            return self._serialize(dataset)

        updates["updated_at"] = datetime.now(timezone.utc)
        updated = self.repo.update_one(dataset_id, updates)
        return self._serialize(updated or dataset)

    def _guess_mapping(self, columns: Sequence[str]) -> Dict[str, Optional[str]]:
        """Best-effort mapping for required fields based on column names."""

        def find_match(options: Sequence[str]) -> Optional[str]:
            lowered = [c.lower() for c in columns]
            for opt in options:
                if opt in lowered:
                    return columns[lowered.index(opt)]
            return None

        return {
            "build_id": find_match(
                ["build_id", "build id", "id", "workflow_run_id", "run_id"]
            ),
            "repo_name": find_match(
                ["repo", "repository", "repo_name", "full_name", "project"]
            ),
        }

    def create_from_upload(
        self,
        user_id: str,
        filename: str,
        upload_file,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DatasetResponse:
        """
        Create a dataset record from an uploaded CSV
        """
        temp_path = DATASET_DIR / f"tmp_{uuid4()}_{filename}"
        size_bytes = 0

        # Stream to disk
        try:
            with temp_path.open("wb") as out_f:
                while True:
                    chunk = upload_file.read(1024 * 1024)
                    if not chunk:
                        break
                    size_bytes += len(chunk)
                    out_f.write(chunk)
        except Exception as exc:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to persist uploaded file: {exc}",
            )

        try:
            df_preview = pd.read_csv(temp_path, nrows=5, dtype=str)

            columns = list(df_preview.columns)
            if not columns:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV header is missing or invalid",
                )

            preview = df_preview.head(3).fillna("").to_dict(orient="records")

            # Read full file for stats calculation
            df_full = pd.read_csv(temp_path, dtype=str)
            row_count = len(df_full)

            # Calculate missing_rate: percentage of empty cells
            total_cells = df_full.size  # rows * columns
            if total_cells > 0:
                empty_cells = df_full.isna().sum().sum() + (df_full == "").sum().sum()
                missing_rate = round((empty_cells / total_cells) * 100, 2)
            else:
                missing_rate = 0.0

            # Calculate duplicate_rate: percentage of duplicate rows
            if row_count > 0:
                duplicate_count = df_full.duplicated().sum()
                duplicate_rate = round((duplicate_count / row_count) * 100, 2)
            else:
                duplicate_rate = 0.0

            stats = DatasetStats(
                missing_rate=missing_rate,
                duplicate_rate=duplicate_rate,
                build_coverage=0.0,  # Calculated after validation
            )

        except HTTPException:
            temp_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse CSV: {exc}",
            )

        mapping = self._guess_mapping(columns)

        now = datetime.now(timezone.utc)

        dataset_entity = DatasetProject(
            user_id=ObjectId(user_id),
            name=name or filename.rsplit(".", 1)[0],
            description=description,
            file_name=filename,
            file_path=str(temp_path.resolve()),
            source="upload",
            rows=row_count,
            size_bytes=size_bytes,
            columns=columns,
            mapped_fields=DatasetMapping(**mapping),
            stats=stats,
            preview=preview,
            created_at=now,
            updated_at=now,
        )

        dataset = self.repo.insert_one(dataset_entity)

        final_path = DATASET_DIR / f"{dataset.id}_{filename}"
        try:
            temp_path.rename(final_path)
            self.repo.update_one(
                str(dataset.id), {"file_path": str(final_path.resolve())}
            )
        except Exception as e:
            logger.warning("Failed to move uploaded dataset file: %s", e)
            # file_path already set to temp_path, so just log warning

        # Dispatch repo validation task if repo_name column is mapped
        if mapping.get("repo_name"):
            from app.tasks.dataset_validation import validate_repos_task

            task = validate_repos_task.delay(str(dataset.id))
            self.repo.update_one(
                str(dataset.id),
                {"repo_validation_task_id": task.id},
            )
            logger.info(
                f"Dispatched repo validation task {task.id} for dataset {dataset.id}"
            )

        return self._serialize(self.repo.find_by_id(str(dataset.id)))

    def delete_dataset(self, dataset_id: str, user_id: str) -> None:
        """Delete a dataset and all associated data."""
        dataset = self.repo.find_by_id(dataset_id)
        if not dataset or (dataset.user_id and str(dataset.user_id) != user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found"
            )

        dataset_oid = ObjectId(dataset_id)

        # Delete associated enrichment_repositories
        self.db.enrichment_repositories.delete_many({"dataset_id": dataset_oid})

        # Delete associated dataset_builds
        self.db.dataset_builds.delete_many({"dataset_id": dataset_oid})

        # Delete the CSV file if exists
        if dataset.file_path:
            try:
                file_path = Path(dataset.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete dataset file: %s", e)

        # Delete the dataset document
        self.repo.delete_one(dataset_id)
