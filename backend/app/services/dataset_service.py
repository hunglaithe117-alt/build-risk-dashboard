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
from app.repositories.dataset_repository import DatasetRepository

logger = logging.getLogger(__name__)
DATASET_DIR = Path("../repo-data/datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)
REQUIRED_MAPPING_FIELDS = ["build_id", "repo_name"]


class DatasetService:
    def __init__(self, db: Database):
        self.db = db
        self.repo = DatasetRepository(db)

    def _serialize(self, dataset) -> DatasetResponse:
        # Ensure nested models are converted to plain data for Pydantic response DTO
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
        if "selected_features" in payload_dict:
            updates["selected_features"] = payload_dict["selected_features"] or []

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
        ci_provider: str = "github_actions",
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

            row_count = (
                sum(1 for _ in open(temp_path, "r", encoding="utf-8", errors="ignore"))
                - 1
            )
            if row_count < 0:
                row_count = 0

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
        coverage = len([v for v in mapping.values() if v]) / 4 if mapping else 0

        now = datetime.now(timezone.utc)

        # Prepare final file path (will be set after moving temp file)
        final_path = DATASET_DIR / f"pending_{uuid4()}_{filename}"

        document: Dict[str, Any] = {
            "user_id": ObjectId(user_id),
            "name": name or filename.rsplit(".", 1)[0],
            "description": description,
            "file_name": filename,
            "file_path": str(final_path.resolve()),
            "source": "upload",
            "ci_provider": ci_provider,
            "rows": row_count,
            "size_bytes": size_bytes,
            "columns": columns,
            "mapped_fields": mapping,
            "stats": {
                "coverage": coverage,
                "missing_rate": 0.0,
                "duplicate_rate": 0.0,
                "build_coverage": coverage,
            },
            "selected_features": [],
            "preview": preview,
            "created_at": now,
            "updated_at": now,
        }

        dataset = self.repo.insert_one(document)

        # Move temp file to final location with dataset ID
        final_path = DATASET_DIR / f"{dataset.id}_{filename}"
        try:
            temp_path.rename(final_path)
        except Exception as e:
            logger.warning("Failed to move uploaded dataset file into place: %s", e)
            # keep temp file if move fails

        return self._serialize(dataset)
