"""
Export Utilities - Common helpers for data export across services.

Provides reusable streaming functions for CSV and JSON export.
Each service uses these helpers with its own format_row function.
"""

import csv
import io
import json
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Set


def stream_csv(
    cursor,
    format_row_fn: Callable[[dict], dict],
    features: Optional[List[str]] = None,
    all_feature_keys: Optional[Set[str]] = None,
    norm_params_map: Optional[Dict[str, Any]] = None,
) -> Generator[str, None, None]:
    """
    Stream CSV data from a MongoDB cursor.

    Args:
        cursor: MongoDB cursor
        format_row_fn: Function to format each document to a row dict
        features: Optional list of specific features to include
        all_feature_keys: Optional set of all feature keys for consistent columns
        norm_params_map: Optional normalization params map

    Yields:
        CSV data chunks
    """
    output = io.StringIO()
    writer = None

    for doc in cursor:
        row = format_row_fn(doc, features, all_feature_keys)

        # Apply normalization if provided
        if norm_params_map:
            row = _apply_normalization(row, norm_params_map)

        if writer is None:
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


def stream_json(
    cursor,
    format_row_fn: Callable[[dict], dict],
    features: Optional[List[str]] = None,
    norm_params_map: Optional[Dict[str, Any]] = None,
) -> Generator[str, None, None]:
    """
    Stream JSON data as an array from a MongoDB cursor.

    Args:
        cursor: MongoDB cursor
        format_row_fn: Function to format each document to a row dict
        features: Optional list of specific features to include
        norm_params_map: Optional normalization params map

    Yields:
        JSON data chunks
    """
    yield "[\n"
    first = True
    for doc in cursor:
        row = format_row_fn(doc, features, None)

        # Apply normalization if provided
        if norm_params_map:
            row = _apply_normalization(row, norm_params_map)

        if not first:
            yield ",\n"
        yield json.dumps(row, default=str)
        first = False
    yield "\n]"


def _apply_normalization(
    row: Dict[str, Any],
    norm_params_map: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Apply normalization to row values.

    Args:
        row: Feature values
        norm_params_map: Pre-calculated normalization parameters

    Returns:
        Normalized row
    """
    from app.services.normalization_service import NormalizationService

    return NormalizationService.normalize_row(row, norm_params_map)


def write_csv_file(
    file_path: Path,
    cursor,
    format_row_fn: Callable[[dict], dict],
    features: Optional[List[str]] = None,
    all_feature_keys: Optional[Set[str]] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    norm_params_map: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Write export to CSV file.

    Args:
        file_path: Output file path
        cursor: MongoDB cursor
        format_row_fn: Function to format each document
        features: Optional list of features to include
        all_feature_keys: All feature keys for consistent columns
        progress_callback: Optional callback(count) for progress updates
        norm_params_map: Optional normalization params map

    Returns:
        Total row count written
    """
    with open(file_path, "w", newline="", encoding="utf-8") as f:
        writer = None
        count = 0

        for doc in cursor:
            row = format_row_fn(doc, features, all_feature_keys)

            # Apply normalization if provided
            if norm_params_map:
                row = _apply_normalization(row, norm_params_map)

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

    return count


def write_json_file(
    file_path: Path,
    cursor,
    format_row_fn: Callable[[dict], dict],
    features: Optional[List[str]] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
    norm_params_map: Optional[Dict[str, Any]] = None,
) -> int:
    """
    Write export to JSON file.

    Args:
        file_path: Output file path
        cursor: MongoDB cursor
        format_row_fn: Function to format each document
        features: Optional list of features to include
        progress_callback: Optional callback(count) for progress updates
        norm_params_map: Optional normalization params map

    Returns:
        Total row count written
    """
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("[\n")
        first = True
        count = 0

        for doc in cursor:
            row = format_row_fn(doc, features, None)

            # Apply normalization if provided
            if norm_params_map:
                row = _apply_normalization(row, norm_params_map)

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

    return count


def format_feature_row(
    doc: dict,
    features: Optional[List[str]] = None,
    all_feature_keys: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Format a build document to a feature row for export.

    Used by ModelRepositoryService and DatasetVersionService.
    Merges both 'features' and 'scan_metrics' fields for export.

    Args:
        doc: MongoDB document (ModelTrainingBuild or EnrichmentBuild)
        features: Optional list of specific features to include
        all_feature_keys: Optional set of all feature keys for consistent columns

    Returns:
        Dict mapping feature names to values
    """
    # Merge features and scan_metrics for export
    feature_dict = doc.get("features", {})
    scan_metrics = doc.get("scan_metrics", {})
    merged = {**feature_dict, **scan_metrics}

    row: Dict[str, Any] = {}

    if features:
        for f in features:
            row[f] = merged.get(f)
    elif all_feature_keys:
        for f in all_feature_keys:
            row[f] = merged.get(f)
    else:
        row.update(merged)

    return row


def format_log_row(
    doc: dict,
    features: Optional[List[str]] = None,
    all_feature_keys: Optional[Set[str]] = None,
) -> Dict[str, Any]:
    """
    Format a system log document for export.

    Used by MonitoringService.

    Args:
        doc: MongoDB log document
        features: Ignored (logs have fixed schema)
        all_feature_keys: Ignored (logs have fixed schema)

    Returns:
        Dict with timestamp, level, source, message, details
    """
    return {
        "timestamp": doc.get("timestamp").isoformat() if doc.get("timestamp") else None,
        "level": doc.get("level", "INFO"),
        "source": doc.get("source", "unknown"),
        "message": doc.get("message", ""),
        "details": json.dumps(doc.get("details")) if doc.get("details") else "",
    }
