"""
Export Service - Business logic for data export.

Supports:
- Streaming export for small datasets (< 1000 rows)
- Background job export for large datasets
- CSV and JSON formats
- Feature filtering, date range, and status filtering
"""

import csv
import io
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Generator, Optional, List, Dict, Any, Set
from bson import ObjectId
from pymongo.database import Database

from app.entities.export_job import ExportJob, ExportFormat, ExportStatus
from app.repositories.export_job import ExportJobRepository

logger = logging.getLogger(__name__)

# Export directory for background jobs
EXPORT_DIR = Path("../repo-data/exports")
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# Threshold for using background job vs streaming
STREAMING_THRESHOLD = 1000


class ExportService:
    """
    Service for exporting build data.

    Usage:
        service = ExportService(db)

        # For small datasets - stream directly
        for chunk in service.stream_export(repo_id, format="csv"):
            yield chunk

        # For large datasets - create background job
        job = service.create_export_job(repo_id, user_id)
        run_export_job.delay(str(job.id))
    """

    def __init__(self, db: Database):
        self.db = db
        self.job_repo = ExportJobRepository(db)

    # =========================================================================
    # Query Building
    # =========================================================================

    def _build_query(
        self,
        repo_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Dict:
        """Build MongoDB query for export."""
        query: Dict[str, Any] = {"repo_id": ObjectId(repo_id)}

        if start_date or end_date:
            query["created_at"] = {}
            if start_date:
                query["created_at"]["$gte"] = start_date
            if end_date:
                query["created_at"]["$lte"] = end_date

        if build_status:
            query["status"] = build_status

        return query

    # =========================================================================
    # Count & Size Estimation
    # =========================================================================

    def estimate_row_count(
        self,
        repo_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> int:
        """Estimate number of rows for export."""
        query = self._build_query(repo_id, start_date, end_date, build_status)
        return self.db.build_samples.count_documents(query)

    def should_use_background_job(
        self,
        repo_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> bool:
        """Determine if background job is needed based on count."""
        count = self.estimate_row_count(repo_id, start_date, end_date, build_status)
        return count > STREAMING_THRESHOLD

    # =========================================================================
    # Job Management
    # =========================================================================

    def create_export_job(
        self,
        repo_id: str,
        user_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> ExportJob:
        """Create a new export job for background processing."""
        job = ExportJob(
            repo_id=ObjectId(repo_id),
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

    # =========================================================================
    # Row Formatting
    # =========================================================================

    # Features that contain commit SHAs - join with #
    COMMIT_LIST_FEATURES = {
        "git_all_built_commits",
        "git_prev_built_commit",
    }

    # Features that contain language/framework lists - join with ,
    LIST_FEATURES = {
        "tr_log_lan_all",
        "tr_log_frameworks_all",
        "gh_lang",
        "source_languages",
    }

    def _format_value(self, key: str, value: Any) -> Any:
        """
        Format a feature value for export.

        - Lists of commit SHAs are joined with '#'
        - Lists of languages/frameworks are joined with ','
        - Other lists are joined with ','
        - Other values are returned as-is
        """
        if value is None:
            return None

        if isinstance(value, list):
            if not value:
                return ""

            # Check if this is a commit list
            if key in self.COMMIT_LIST_FEATURES:
                return "#".join(str(v) for v in value)

            # All other lists use comma separator
            return ",".join(str(v) for v in value)

        return value

    def _format_row(
        self,
        doc: dict,
        features: Optional[List[str]] = None,
        all_feature_keys: Optional[Set[str]] = None,
    ) -> dict:
        """
        Format a MongoDB document as an export row.

        Args:
            doc: MongoDB document
            features: Optional list of specific features to include
            all_feature_keys: Optional set of all feature keys for consistent columns
        """
        # Base fields
        row = {
            "build_id": str(doc["_id"]),
            "workflow_run_id": doc.get("workflow_run_id"),
            "status": doc.get("status"),
            "extraction_status": doc.get("extraction_status"),
            "error_message": doc.get("error_message"),
            "is_missing_commit": doc.get("is_missing_commit", False),
            "created_at": (
                doc.get("created_at").isoformat() if doc.get("created_at") else None
            ),
        }

        # Add features with proper formatting
        feature_dict = doc.get("features", {})

        if features:
            # Only requested features
            for f in features:
                raw_value = feature_dict.get(f)
                row[f] = self._format_value(f, raw_value)
        elif all_feature_keys:
            # All features with consistent keys
            for f in all_feature_keys:
                raw_value = feature_dict.get(f)
                row[f] = self._format_value(f, raw_value)
        else:
            # All features from this document
            for f, raw_value in feature_dict.items():
                row[f] = self._format_value(f, raw_value)

        return row

    def _get_all_feature_keys(
        self,
        repo_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Set[str]:
        """
        Get all unique feature keys across all builds.

        This ensures consistent CSV columns even when some builds
        have different features.
        """
        query = self._build_query(repo_id, start_date, end_date, build_status)

        pipeline = [
            {"$match": query},
            {"$project": {"feature_keys": {"$objectToArray": "$features"}}},
            {"$unwind": "$feature_keys"},
            {"$group": {"_id": None, "keys": {"$addToSet": "$feature_keys.k"}}},
        ]

        result = list(self.db.build_samples.aggregate(pipeline))
        if result:
            return set(result[0].get("keys", []))
        return set()

    # =========================================================================
    # Streaming Export (for small datasets)
    # =========================================================================

    def stream_export(
        self,
        repo_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Generator[str, None, None]:
        """
        Stream export data for small datasets.

        Yields chunks of CSV or JSON data.
        """
        query = self._build_query(repo_id, start_date, end_date, build_status)

        # For CSV, get all feature keys first for consistent columns
        all_feature_keys = None
        if format == "csv" and not features:
            all_feature_keys = self._get_all_feature_keys(
                repo_id, start_date, end_date, build_status
            )

        cursor = self.db.build_samples.find(query).sort("created_at", 1).batch_size(100)

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
        progress_callback: Optional[callable] = None,
    ) -> Path:
        """
        Write export to file for background job.

        Args:
            job: Export job with filters
            progress_callback: Optional callback(processed_rows) for progress updates

        Returns:
            Path to the generated file
        """
        file_name = f"{job.id}.{job.format}"
        file_path = EXPORT_DIR / file_name

        query = self._build_query(
            str(job.repo_id), job.start_date, job.end_date, job.build_status
        )

        # Get all feature keys for consistent columns
        all_feature_keys = None
        if job.format == "csv" and not job.features:
            all_feature_keys = self._get_all_feature_keys(
                str(job.repo_id),
                job.start_date,
                job.end_date,
                job.build_status,
            )

        cursor = self.db.build_samples.find(query).sort("created_at", 1).batch_size(100)

        if job.format == "csv":
            self._write_csv_file(
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
