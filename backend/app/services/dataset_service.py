import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, Sequence
from uuid import uuid4

import pandas as pd
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import (
    DatasetCreateRequest,
    DatasetListResponse,
    DatasetResponse,
)
from app.entities.dataset import DatasetMapping, DatasetProject, DatasetStats
from app.repositories.dataset_build_repository import DatasetBuildRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository
from app.repositories.dataset_import_build import DatasetImportBuildRepository
from app.repositories.dataset_repository import DatasetRepository

logger = logging.getLogger(__name__)
DATASET_DIR = Path("../repo-data/datasets")
DATASET_DIR.mkdir(parents=True, exist_ok=True)
REQUIRED_MAPPING_FIELDS = ["build_id", "repo_name"]


class DatasetService:
    def __init__(self, db: Database):
        self.db = db
        self.repo = DatasetRepository(db)
        self.build_repo = DatasetBuildRepository(db)
        self.enrichment_build_repo = DatasetEnrichmentBuildRepository(db)
        self.import_build_repo = DatasetImportBuildRepository(db)

    def _serialize(self, dataset) -> DatasetResponse:
        payload = dataset.model_dump(by_alias=True) if hasattr(dataset, "model_dump") else dataset
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
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
    ) -> DatasetListResponse:
        """
        List datasets.

        Permission is validated at API layer via RequirePermission middleware.
        """
        datasets, total = self.repo.list_by_user(None, skip=skip, limit=limit, q=q)
        return DatasetListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=[self._serialize(ds) for ds in datasets],
        )

    def get_dataset(self, dataset_id: str, user_id: str) -> DatasetResponse:
        """Get dataset details. Permission validated at API layer."""
        dataset = self.repo.find_by_id(dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")
        return self._serialize(dataset)

    def create_dataset(self, user_id: str, payload: DatasetCreateRequest) -> DatasetResponse:
        now = datetime.now(timezone.utc)
        data = payload.model_dump(exclude_none=True)
        data["user_id"] = ObjectId(user_id) if user_id else None
        data["created_at"] = now
        data["updated_at"] = now
        if data.get("mapped_fields") and data.get("columns"):
            self._validate_required_mapping(data["mapped_fields"], data["columns"])
        dataset = self.repo.insert_one(data)
        return self._serialize(dataset)

    def _guess_mapping(self, columns: Sequence[str]) -> Dict[str, Optional[str]]:
        """Best-effort mapping for required fields based on column names."""

        def find_match(options: Sequence[str]) -> Optional[str]:
            lowered = [c.lower() for c in columns]
            for opt in options:
                if opt in lowered:
                    return columns[lowered.index(opt)]
            return None

        return {
            "build_id": find_match(["build_id", "build id", "id", "ci_run_id", "run_id"]),
            "repo_name": find_match(["repo", "repository", "repo_name", "full_name", "project"]),
        }

    def create_from_upload(
        self,
        user_id: str,
        filename: Optional[str],
        upload_file,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> DatasetResponse:
        """
        Create a dataset record from an uploaded CSV
        """
        if not filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Filename is required",
            )

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
            logger.error(f"Upload failed: {str(exc)}", exc_info=True)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to save uploaded file: {str(exc)}",
            ) from exc

        try:
            df_preview = pd.read_csv(temp_path, nrows=5, dtype=str)

            columns = list(df_preview.columns)
            if not columns:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="CSV header is missing or invalid",
                )

            preview = df_preview.head(3).fillna("").to_dict(orient="records")

            # Calculate stats using chunks to avoid OOM
            row_count = 0
            total_cells = 0
            empty_cells = 0

            # Note: Global duplicate check is expensive for large files, skipping/simplifying
            # We could implement a bloom filter or hash set if stricter validation is needed

            for chunk in pd.read_csv(temp_path, dtype=str, chunksize=10000):
                row_count += len(chunk)
                total_cells += chunk.size
                empty_cells += chunk.isna().sum().sum() + (chunk == "").sum().sum()

            # Calculate missing_rate
            if total_cells > 0:
                missing_rate = round((empty_cells / total_cells) * 100, 2)
            else:
                missing_rate = 0.0

            duplicate_rate = 0.0  # Placeholder, skipping expensive global duplicate check

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
                detail="Unable to parse your CSV file. Please check the format and try again.",
            ) from exc

        mapping = self._guess_mapping(columns)

        now = datetime.now(timezone.utc)

        dataset_entity = DatasetProject(
            _id=None,
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
            self.repo.update_one(str(dataset.id), {"file_path": str(final_path.resolve())})
        except Exception as e:
            logger.warning("Failed to move uploaded dataset file: %s", e)
            # file_path already set to temp_path, so just log warning

        # Dispatch unified validation task if required columns are mapped
        if mapping.get("repo_name") and mapping.get("build_id"):
            from app.tasks.dataset_validation import (
                dataset_validation_orchestrator,
            )

            task = dataset_validation_orchestrator.delay(str(dataset.id))
            self.repo.update_one(
                str(dataset.id),
                {"validation_task_id": task.id, "validation_status": "validating"},
            )
            logger.info(
                f"Dispatched distributed validation task {task.id} for dataset {dataset.id}"
            )

        return self._serialize(self.repo.find_by_id(str(dataset.id)))

    def delete_dataset(self, dataset_id: str, user_id: str) -> None:
        """Delete a dataset and all associated data atomically using transaction."""
        from app.database.mongo import get_transaction
        from app.repositories.dataset_repo_stats import DatasetRepoStatsRepository
        from app.repositories.dataset_version import DatasetVersionRepository
        from app.repositories.feature_audit_log import FeatureAuditLogRepository

        dataset = self.repo.find_by_id(dataset_id)
        if not dataset or (dataset.user_id and str(dataset.user_id) != user_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        dataset_oid = ObjectId(dataset_id)
        repo_stats_repo = DatasetRepoStatsRepository(self.db)
        version_repo = DatasetVersionRepository(self.db)
        audit_log_repo = FeatureAuditLogRepository(self.db)

        # Use transaction to ensure all deletes happen atomically
        with get_transaction() as session:
            # 1. Delete associated FeatureAuditLogs
            audit_deleted = audit_log_repo.delete_by_dataset_id(dataset_id, session=session)
            logger.info(f"Deleted {audit_deleted} audit logs for dataset {dataset_id}")

            # 2. Delete associated enrichment builds (DatasetEnrichmentBuild)
            deleted_enrichment = self.enrichment_build_repo.delete_by_dataset(
                dataset_oid, session=session
            )
            logger.info(f"Deleted {deleted_enrichment} enrichment builds for dataset {dataset_id}")

            # 3. Delete associated import builds (DatasetImportBuild)
            deleted_import = self.import_build_repo.delete_by_dataset(dataset_oid, session=session)
            logger.info(f"Deleted {deleted_import} import builds for dataset {dataset_id}")

            # Delete associated dataset builds (DatasetBuild)
            deleted_builds = self.build_repo.delete_by_dataset(dataset_id, session=session)
            logger.info(f"Deleted {deleted_builds} dataset builds for dataset {dataset_id}")

            # Delete repo stats (DatasetRepoStats)
            deleted_stats = repo_stats_repo.delete_by_dataset(dataset_id, session=session)
            logger.info(f"Deleted {deleted_stats} repo stats for dataset {dataset_id}")

            # Delete versions (DatasetVersion)
            deleted_versions = version_repo.delete_by_dataset(dataset_id, session=session)
            logger.info(f"Deleted {deleted_versions} versions for dataset {dataset_id}")

            # Delete the dataset document (DatasetProject)
            self.repo.delete_one(dataset_id, session=session)
            logger.info(f"Deleted dataset {dataset_id}")

        # Delete the CSV file outside transaction (not a DB operation)
        if dataset.file_path:
            try:
                file_path = Path(dataset.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete dataset file: %s", e)

    def update_dataset(
        self,
        dataset_id: str,
        user_id: str,
        updates: dict,
    ) -> DatasetResponse:
        """
        Update dataset fields (PATCH operation).

        Allows updating:
        - name, description
        - mapped_fields (build_id, repo_name columns)
        - ci_provider
        - build_filters (exclude_bots, only_completed, allowed_conclusions)
        - setup_step
        """
        from app.entities.dataset import BuildValidationFilters, DatasetValidationStatus

        dataset = self.repo.find_by_id(dataset_id)
        if not dataset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found")

        # Block config changes if validation is completed
        # These fields affect which builds are validated, so changing them
        # after validation would invalidate the results
        if dataset.validation_status == DatasetValidationStatus.COMPLETED:
            config_fields = ["mapped_fields", "ci_provider", "build_filters"]
            if any(updates.get(f) is not None for f in config_fields):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot update configuration after validation is completed. "
                    "Delete and re-upload the dataset to change configuration.",
                )

        # Build update dict with only non-None values
        update_data = {}
        now = datetime.now(timezone.utc)
        update_data["updated_at"] = now

        if updates.get("name") is not None:
            update_data["name"] = updates["name"]

        if updates.get("description") is not None:
            update_data["description"] = updates["description"]

        if updates.get("mapped_fields") is not None:
            mf = updates["mapped_fields"]
            # Convert DTO to entity if needed
            if hasattr(mf, "model_dump"):
                mf = mf.model_dump()
            update_data["mapped_fields"] = DatasetMapping(**mf).model_dump()

        if updates.get("ci_provider") is not None:
            update_data["ci_provider"] = updates["ci_provider"]

        if updates.get("build_filters") is not None:
            bf = updates["build_filters"]
            if hasattr(bf, "model_dump"):
                bf = bf.model_dump()
            update_data["build_filters"] = BuildValidationFilters(**bf).model_dump()

        if updates.get("setup_step") is not None:
            update_data["setup_step"] = updates["setup_step"]

        # Apply updates
        self.repo.update_one(dataset_id, update_data)

        return self._serialize(self.repo.find_by_id(dataset_id))

    def get_dataset_builds(
        self,
        dataset_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 50,
        status_filter: Optional[str] = None,
        q: Optional[str] = None,
    ) -> dict:
        """
        List builds for a dataset with enriched details from RawBuildRun.

        Returns paginated list of builds with RawBuildRun enrichment.
        """
        import re

        from app.repositories.raw_build_run import RawBuildRunRepository

        # Access check and dataset existence
        self.get_dataset(dataset_id, user_id)

        raw_build_repo = RawBuildRunRepository(self.db)
        dataset_oid = ObjectId(dataset_id)

        # Build query
        query: Dict = {"dataset_id": dataset_oid}
        if status_filter:
            query["status"] = status_filter

        # Add search filter
        if q:
            search_regex = re.compile(re.escape(q), re.IGNORECASE)
            query["$or"] = [
                {"repo_name_from_csv": {"$regex": search_regex}},
                {"build_id_from_csv": {"$regex": search_regex}},
            ]

        # Get total and items
        total = self.build_repo.count_by_query(query)
        builds = self.build_repo.find_by_query(
            query, skip=skip, limit=limit, sort_by="validated_at"
        )

        items = []
        for build in builds:
            build_item = {
                "id": str(build.id),
                "build_id_from_csv": build.build_id_from_csv,
                "repo_name_from_csv": build.repo_name_from_csv,
                "status": build.status,
                "validation_error": build.validation_error,
                "validated_at": build.validated_at,
            }

            # Enrich with RawBuildRun data if available
            if build.raw_run_id:
                raw_build = raw_build_repo.find_by_id(build.raw_run_id)
                if raw_build:
                    build_item.update(
                        {
                            "build_number": raw_build.build_number,
                            "branch": raw_build.branch,
                            "commit_sha": raw_build.commit_sha,
                            "commit_message": raw_build.commit_message,
                            "commit_author": raw_build.commit_author,
                            "conclusion": raw_build.conclusion,
                            "started_at": raw_build.started_at,
                            "completed_at": raw_build.completed_at,
                            "duration_seconds": raw_build.duration_seconds,
                            "logs_available": raw_build.logs_available,
                            "web_url": raw_build.web_url,
                        }
                    )

            items.append(build_item)

        return {
            "items": items,
            "total": total,
            "skip": skip,
            "limit": limit,
        }

    def get_dataset_builds_stats(
        self,
        dataset_id: str,
        user_id: str,
    ) -> dict:
        """
        Get aggregated build stats for charts.

        Returns status breakdown, conclusion breakdown, builds per repo, duration stats,
        and logs availability statistics.
        Permission validated at API layer.
        """
        # Access check (raises if not permitted)
        self.get_dataset(dataset_id, user_id)

        dataset_oid = ObjectId(dataset_id)

        # Status breakdown (for pie chart)
        status_pipeline = [
            {"$match": {"dataset_id": dataset_oid}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        status_counts = list(self.db.dataset_builds.aggregate(status_pipeline))
        status_breakdown = {item["_id"]: item["count"] for item in status_counts}

        # Get validated builds for conclusion breakdown
        validated_builds = list(
            self.db.dataset_builds.find(
                {"dataset_id": dataset_oid, "status": "found", "raw_run_id": {"$ne": None}},
                {"raw_run_id": 1},
            )
        )

        workflow_run_ids = [b["raw_run_id"] for b in validated_builds if b.get("raw_run_id")]

        # Conclusion breakdown from RawBuildRun
        conclusion_breakdown = {}
        if workflow_run_ids:
            conclusion_pipeline = [
                {"$match": {"_id": {"$in": workflow_run_ids}}},
                {"$group": {"_id": "$conclusion", "count": {"$sum": 1}}},
            ]
            conclusion_counts = list(self.db.raw_build_runs.aggregate(conclusion_pipeline))
            conclusion_breakdown = {item["_id"]: item["count"] for item in conclusion_counts}

        # Builds per repo (for bar chart)
        repo_pipeline = [
            {"$match": {"dataset_id": dataset_oid, "status": "found"}},
            {"$group": {"_id": "$repo_name_from_csv", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 10},
        ]
        repo_counts = list(self.db.dataset_builds.aggregate(repo_pipeline))
        builds_per_repo = [{"repo": item["_id"], "count": item["count"]} for item in repo_counts]

        # Duration stats
        avg_duration = None
        if workflow_run_ids:
            duration_result = list(
                self.db.raw_build_runs.aggregate(
                    [
                        {
                            "$match": {
                                "_id": {"$in": workflow_run_ids},
                                "duration_seconds": {"$ne": None},
                            }
                        },
                        {"$group": {"_id": None, "avg": {"$avg": "$duration_seconds"}}},
                    ]
                )
            )
            if duration_result:
                avg_duration = duration_result[0]["avg"]

        # Logs availability
        logs_stats = {"available": 0, "unavailable": 0, "expired": 0}
        if workflow_run_ids:
            logs_pipeline = [
                {"$match": {"_id": {"$in": workflow_run_ids}}},
                {
                    "$group": {
                        "_id": None,
                        "available": {
                            "$sum": {"$cond": [{"$eq": ["$logs_available", True]}, 1, 0]}
                        },
                        "expired": {"$sum": {"$cond": [{"$eq": ["$logs_expired", True]}, 1, 0]}},
                        "total": {"$sum": 1},
                    }
                },
            ]
            logs_result = list(self.db.raw_build_runs.aggregate(logs_pipeline))
            if logs_result:
                logs_stats["available"] = logs_result[0].get("available", 0)
                logs_stats["expired"] = logs_result[0].get("expired", 0)
                logs_stats["unavailable"] = (
                    logs_result[0]["total"] - logs_stats["available"] - logs_stats["expired"]
                )

        return {
            "status_breakdown": status_breakdown,
            "conclusion_breakdown": conclusion_breakdown,
            "builds_per_repo": builds_per_repo,
            "avg_duration_seconds": avg_duration,
            "logs_stats": logs_stats,
            "total_builds": sum(status_breakdown.values()),
            "found_builds": status_breakdown.get("found", 0),
        }
