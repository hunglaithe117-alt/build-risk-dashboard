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
    """

    def __init__(self, db: Database):
        self.db = db
        self.job_repo = ExportJobRepository(db)

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

    def _format_row(
        self,
        doc: dict,
        features: Optional[List[str]] = None,
        all_feature_keys: Optional[Set[str]] = None,
    ) -> dict:
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
        repo_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        build_status: Optional[str] = None,
    ) -> Set[str]:
        query = self._build_query(repo_id, start_date, end_date, build_status)

        pipeline = [
            {"$match": query},
            {"$project": {"feature_keys": {"$objectToArray": "$features"}}},
            {"$unwind": {"path": "$feature_keys", "preserveNullAndEmptyArrays": False}},
            {"$group": {"_id": None, "keys": {"$addToSet": "$feature_keys.k"}}},
        ]

        result = list(self.db.build_samples.aggregate(pipeline))
        if result:
            return set(result[0].get("keys", []))
        return set()

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
