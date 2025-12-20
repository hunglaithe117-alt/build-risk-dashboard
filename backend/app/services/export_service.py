"""
Export Service - Business logic for data export.

Supports:
- Streaming export for small datasets (< 1000 rows)
- Background job export for large datasets
- CSV, JSON, and Parquet formats
- Feature filtering, date range, and status filtering
- Both model_builds (repo imports) and enrichment_builds (dataset versions)
"""

import csv
import io
import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set

from bson import ObjectId
from pymongo.database import Database

from app.entities.export_job import ExportJob
from app.repositories.export_job import ExportJobRepository

logger = logging.getLogger(__name__)

# Export directory for background jobs
EXPORT_DIR = Path("../repo-data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Threshold for using background job vs streaming
STREAMING_THRESHOLD = 1000


class ExportSource(str, Enum):
    """Data source for export."""

    MODEL_BUILDS = "model_builds"
    ENRICHMENT_BUILDS = "enrichment_builds"


class ExportService:
    """
    Service for exporting build data.

    Supports both:
    - model_builds: from repo imports (ML prediction workflow)
    - enrichment_builds: from dataset enrichment (dataset versioning workflow)
    """

    def __init__(self, db: Database):
        self.db = db
        self.job_repo = ExportJobRepository(db)

    def _get_collection(self, source: ExportSource):
        """Get the MongoDB collection for the given source."""
        if source == ExportSource.ENRICHMENT_BUILDS:
            return self.db.enrichment_builds
        return self.db.model_training_builds

    def _build_query(
        self,
        source: ExportSource,
        repo_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Dict:
        """Build MongoDB query for export."""
        query: Dict[str, Any] = {}

        if source == ExportSource.ENRICHMENT_BUILDS:
            if dataset_id:
                query["dataset_id"] = ObjectId(dataset_id)
            if version_id:
                query["version_id"] = ObjectId(version_id)
        else:
            # repo_id is the ModelRepoConfig._id
            if repo_id:
                query["model_repo_config_id"] = ObjectId(repo_id)

        if start_date or end_date:
            query["created_at"] = {}
            if start_date:
                query["created_at"]["$gte"] = start_date
            if end_date:
                query["created_at"]["$lte"] = end_date

        if build_status:
            query["status"] = build_status

        return query

    def estimate_row_count(
        self,
        source: ExportSource = ExportSource.MODEL_BUILDS,
        repo_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> int:
        """Estimate number of rows for export."""
        query = self._build_query(
            source, repo_id, dataset_id, version_id, start_date, end_date, build_status
        )
        collection = self._get_collection(source)
        return collection.count_documents(query)

    def should_use_background_job(
        self,
        source: ExportSource = ExportSource.MODEL_BUILDS,
        repo_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> bool:
        """Determine if background job is needed based on count."""
        count = self.estimate_row_count(
            source, repo_id, dataset_id, version_id, start_date, end_date, build_status
        )
        return count > STREAMING_THRESHOLD

    def create_export_job(
        self,
        user_id: str,
        format: str = "csv",
        source: ExportSource = ExportSource.MODEL_BUILDS,
        repo_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        features: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> ExportJob:
        """Create a new export job for background processing."""
        job = ExportJob(
            repo_id=ObjectId(repo_id) if repo_id else None,
            user_id=ObjectId(user_id),
            format=format,
            features=features,
            start_date=start_date,
            end_date=end_date,
            build_status=build_status,
        )
        return self.job_repo.create(job)

    def get_export_file_path(self, job_id: str) -> Optional[Path]:
        """Get the file path for a completed export."""
        job = self.job_repo.find_by_id(job_id)
        if job and job.file_path:
            path = Path(job.file_path)
            if path.exists():
                return path
        return None

    def _format_row(
        self,
        doc: dict,
        features: Optional[List[str]] = None,
        all_feature_keys: Optional[Set[str]] = None,
    ) -> dict:
        """Format a document row for export."""
        feature_dict = doc.get("features", {})
        row = {}

        if features:
            for f in features:
                row[f] = feature_dict.get(f)
        elif all_feature_keys:
            for f in all_feature_keys:
                row[f] = feature_dict.get(f)
        else:
            row.update(feature_dict)

        return row

    def _get_all_feature_keys(
        self,
        source: ExportSource,
        repo_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Set[str]:
        """Get all unique feature keys from documents."""
        query = self._build_query(
            source, repo_id, dataset_id, version_id, start_date, end_date, build_status
        )
        collection = self._get_collection(source)

        pipeline = [
            {"$match": query},
            {"$project": {"feature_keys": {"$objectToArray": "$features"}}},
            {"$unwind": {"path": "$feature_keys", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": None, "keys": {"$addToSet": "$feature_keys.k"}}},
        ]

        result = list(collection.aggregate(pipeline))
        if result:
            return set(result[0].get("keys", []))
        return set()

    def stream_export(
        self,
        format: str = "csv",
        source: ExportSource = ExportSource.MODEL_BUILDS,
        repo_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        features: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Stream export data for small datasets.

        Yields chunks of CSV or JSON data.
        """
        query = self._build_query(
            source, repo_id, dataset_id, version_id, start_date, end_date, build_status
        )
        collection = self._get_collection(source)

        # For CSV, get all feature keys first for consistent columns
        all_feature_keys = None
        if format == "csv" and not features:
            all_feature_keys = self._get_all_feature_keys(
                source,
                repo_id,
                dataset_id,
                version_id,
                start_date,
                end_date,
                build_status,
            )

        cursor = collection.find(query).sort("created_at", 1).batch_size(100)

        if format == "csv":
            yield from self._stream_csv(cursor, features, all_feature_keys)
        else:
            yield from self._stream_json(cursor, features)

    def _stream_csv(
        self,
        cursor,
        features: Optional[List[str]],
        all_feature_keys: Optional[Set[str]] = None,
    ) -> Generator[str, None, None]:
        """Stream CSV data."""
        output = io.StringIO()
        writer = None

        for doc in cursor:
            row = self._format_row(doc, features, all_feature_keys)

            if writer is None:
                # Consistent column order
                fieldnames = list(row.keys())
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

            writer.writerow(row)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    def _stream_json(
        self,
        cursor,
        features: Optional[List[str]],
    ) -> Generator[str, None, None]:
        """Stream JSON data as an array."""
        yield "[\n"
        first = True
        for doc in cursor:
            row = self._format_row(doc, features)
            if not first:
                yield ",\n"
            yield json.dumps(row, default=str)
            first = False
        yield "\n]"

    # =========================================================================
    # Background Export (for large datasets)
    # =========================================================================

    def write_export_file(
        self,
        job: ExportJob,
        source: ExportSource = ExportSource.MODEL_BUILDS,
        dataset_id: Optional[str] = None,
        version_id: Optional[str] = None,
        progress_callback: Optional[callable] = None,
    ) -> Path:
        """
        Write export to file for background job.

        Args:
            job: Export job with filters
            source: Data source (model_builds or enrichment_builds)
            dataset_id: Dataset ID for enrichment exports
            version_id: Version ID for enrichment exports
            progress_callback: Optional callback(processed_rows) for progress updates

        Returns:
            Path to the generated file
        """
        file_name = f"{job.id}.{job.format}"
        file_path = EXPORT_DIR / file_name

        query = self._build_query(
            source,
            str(job.repo_id) if job.repo_id else None,
            dataset_id,
            version_id,
            job.start_date,
            job.end_date,
            job.build_status,
        )
        collection = self._get_collection(source)

        # Get all feature keys for consistent columns
        all_feature_keys = None
        if job.format == "csv" and not job.features:
            all_feature_keys = self._get_all_feature_keys(
                source,
                str(job.repo_id) if job.repo_id else None,
                dataset_id,
                version_id,
                job.start_date,
                job.end_date,
                job.build_status,
            )

        cursor = collection.find(query).sort("created_at", 1).batch_size(100)

        if job.format == "csv":
            self._write_csv_file(
                file_path, cursor, job.features, all_feature_keys, progress_callback
            )
        elif job.format == "parquet":
            self._write_parquet_file(
                file_path, cursor, job.features, all_feature_keys, progress_callback
            )
        else:
            self._write_json_file(file_path, cursor, job.features, progress_callback)

        return file_path

    def _write_csv_file(
        self,
        file_path: Path,
        cursor,
        features: Optional[List[str]],
        all_feature_keys: Optional[Set[str]],
        progress_callback: Optional[callable],
    ) -> None:
        """Write CSV export file."""
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = None
            count = 0

            for doc in cursor:
                row = self._format_row(doc, features, all_feature_keys)

                if writer is None:
                    fieldnames = list(row.keys())
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()

                writer.writerow(row)
                count += 1

                if progress_callback and count % 100 == 0:
                    progress_callback(count)

            if progress_callback:
                progress_callback(count)

    def _write_json_file(
        self,
        file_path: Path,
        cursor,
        features: Optional[List[str]],
        progress_callback: Optional[callable],
    ) -> None:
        """Write JSON export file."""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("[\n")
            first = True
            count = 0

            for doc in cursor:
                row = self._format_row(doc, features)
                if not first:
                    f.write(",\n")
                f.write(json.dumps(row, default=str, indent=2))
                first = False
                count += 1

                if progress_callback and count % 100 == 0:
                    progress_callback(count)

            f.write("\n]")

            if progress_callback:
                progress_callback(count)

    def _write_parquet_file(
        self,
        file_path: Path,
        cursor,
        features: Optional[List[str]],
        all_feature_keys: Optional[Set[str]],
        progress_callback: Optional[callable],
    ) -> None:
        """Write Parquet export file."""
        import pandas as pd

        rows = []
        count = 0

        for doc in cursor:
            row = self._format_row(doc, features, all_feature_keys)
            rows.append(row)
            count += 1

            if progress_callback and count % 100 == 0:
                progress_callback(count)

        df = pd.DataFrame(rows)
        df.to_parquet(file_path, engine="pyarrow", compression="snappy", index=False)

        if progress_callback:
            progress_callback(count)

    def export_enrichment_version(
        self,
        dataset_id: str,
        version_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
    ) -> Generator[str, None, None]:
        """
        Stream export for a specific dataset version.

        Args:
            dataset_id: Dataset ID
            version_id: Version ID
            format: Export format (csv, json)
            features: Optional list of features to include

        Yields:
            Chunks of export data
        """
        return self.stream_export(
            format=format,
            source=ExportSource.ENRICHMENT_BUILDS,
            dataset_id=dataset_id,
            version_id=version_id,
            features=features,
        )

    def get_enrichment_preview(
        self,
        dataset_id: str,
        version_id: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        Get preview data for an enrichment version.

        Returns:
            Dict with total_rows, sample_rows, available_features
        """
        query = self._build_query(
            ExportSource.ENRICHMENT_BUILDS,
            dataset_id=dataset_id,
            version_id=version_id,
        )
        collection = self._get_collection(ExportSource.ENRICHMENT_BUILDS)

        total_rows = collection.count_documents(query)
        cursor = collection.find(query).limit(limit)

        sample_rows = []
        all_features = set()

        for doc in cursor:
            row = self._format_row(doc)
            sample_rows.append(row)
            all_features.update(row.keys())

        return {
            "total_rows": total_rows,
            "sample_rows": sample_rows,
            "available_features": sorted(all_features),
            "feature_count": len(all_features),
        }

    def get_export_preview(
        self,
        repo_id: Optional[str] = None,
        features: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
        sample_limit: int = 5,
    ) -> Dict[str, Any]:
        """
        Get preview of exportable data for a repository (model_builds).

        Returns:
            Dict with total_rows, use_async_recommended, sample_rows, available_features
        """
        source = ExportSource.MODEL_BUILDS

        count = self.estimate_row_count(
            source=source,
            repo_id=repo_id,
            start_date=start_date,
            end_date=end_date,
            build_status=build_status,
        )

        use_async = self.should_use_background_job(
            source=source,
            repo_id=repo_id,
            start_date=start_date,
            end_date=end_date,
            build_status=build_status,
        )

        # Get sample rows
        query = self._build_query(
            source,
            repo_id=repo_id,
            start_date=start_date,
            end_date=end_date,
            build_status=build_status,
        )
        collection = self._get_collection(source)
        sample_docs = list(collection.find(query).sort("created_at", 1).limit(sample_limit))

        feature_list = features.split(",") if isinstance(features, str) else features
        sample_rows = [self._format_row(doc, feature_list) for doc in sample_docs]

        # Get available features
        available_features = list(
            self._get_all_feature_keys(
                source,
                repo_id=repo_id,
                start_date=start_date,
                end_date=end_date,
                build_status=build_status,
            )
        )

        return {
            "total_rows": count,
            "use_async_recommended": use_async,
            "async_threshold": STREAMING_THRESHOLD,
            "sample_rows": sample_rows,
            "available_features": sorted(available_features),
            "feature_count": len(available_features),
        }
