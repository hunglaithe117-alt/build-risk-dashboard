"""
Shared event publishing utilities for real-time WebSocket updates.

This module provides functions to publish events to Redis pub/sub,
which are then forwarded to WebSocket clients by the API layer.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import redis

from app.config import settings

logger = logging.getLogger(__name__)

# Redis channel for WebSocket events
EVENTS_CHANNEL = "events"


def _get_redis_client():
    """Get a synchronous Redis client."""
    return redis.from_url(settings.REDIS_URL)


def publish_event(event_type: str, payload: Dict[str, Any]) -> bool:
    """
    Publish an event to the Redis events channel.

    Args:
        event_type: Event type (e.g., "REPO_UPDATE", "BUILD_UPDATE")
        payload: Event payload data

    Returns:
        True if published successfully, False otherwise
    """
    try:
        redis_client = _get_redis_client()
        message = json.dumps({"type": event_type, "payload": payload})
        result = redis_client.publish(EVENTS_CHANNEL, message)
        logger.info(f"Published {event_type} to {result} subscribers: {payload}")
        return True
    except Exception as e:
        logger.error(f"Failed to publish event {event_type}: {e}")
        return False


def publish_repo_status(
    repo_id: str,
    status: str,
    message: str = "",
    stats: Optional[Dict[str, int]] = None,
) -> bool:
    """
    Publish repository status update for real-time UI updates.

    Args:
        repo_id: Repository ID (ModelRepoConfig._id or raw_repo_id)
        status: Status value (queued, importing, processing, imported, failed)
        message: Optional status message
        stats: Optional stats to include (total_builds_imported, etc.)

    Returns:
        True if published successfully, False otherwise
    """
    payload = {
        "repo_id": repo_id,
        "status": status,
        "message": message,
    }
    if stats:
        payload["stats"] = stats

    return publish_event("REPO_UPDATE", payload)


def publish_build_status(repo_id: str, build_id: str, status: str) -> bool:
    """
    Publish build status update for real-time UI updates.

    Args:
        repo_id: Repository ID
        build_id: Build ID
        status: Build status (pending, in_progress, completed, failed)

    Returns:
        True if published successfully, False otherwise
    """
    payload = {
        "repo_id": repo_id,
        "build_id": build_id,
        "status": status,
    }
    return publish_event("BUILD_UPDATE", payload)


def publish_enrichment_update(
    version_id: str,
    status: str,
    builds_processed: int = 0,
    builds_total: int = 0,
    builds_ingested: int = 0,
    builds_missing_resource: int = 0,
    builds_ingestion_failed: int = 0,
    error: Optional[str] = None,
) -> bool:
    """
    Publish enrichment progress update for real-time UI updates.

    Args:
        version_id: DatasetVersion ID
        status: Status value (ingesting, processing, completed, failed)
        builds_processed: Number of builds processed so far
        builds_total: Total number of builds in version
        builds_ingested: Number of builds ingested
        builds_missing_resource: Number of builds with missing resources
        builds_ingestion_failed: Number of builds that failed ingestion (retryable)
        error: Optional error message

    Returns:
        True if published successfully, False otherwise
    """
    progress = round((builds_processed / builds_total) * 100, 1) if builds_total > 0 else 0
    payload = {
        "version_id": version_id,
        "status": status,
        "builds_processed": builds_processed,
        "builds_total": builds_total,
        "builds_ingested": builds_ingested,
        "builds_missing_resource": builds_missing_resource,
        "builds_ingestion_failed": builds_ingestion_failed,
        "progress": progress,
    }
    if error:
        payload["error"] = error

    return publish_event("ENRICHMENT_UPDATE", payload)


def publish_scan_update(
    version_id: str,
    scan_id: str,
    commit_sha: str,
    tool_type: str,
    status: str,
    error: Optional[str] = None,
    metrics: Optional[Dict[str, Any]] = None,
    builds_affected: int = 0,
) -> bool:
    """
    Publish scan status update for real-time UI updates.

    Args:
        version_id: DatasetVersion ID
        scan_id: Scan record ID (TrivyCommitScan or SonarCommitScan)
        commit_sha: The commit SHA being scanned
        tool_type: "trivy" or "sonarqube"
        status: Scan status (pending, scanning, completed, failed)
        error: Optional error message
        metrics: Optional scan metrics
        builds_affected: Number of builds updated with scan results

    Returns:
        True if published successfully, False otherwise
    """
    payload = {
        "version_id": version_id,
        "scan_id": scan_id,
        "commit_sha": commit_sha,
        "tool_type": tool_type,
        "status": status,
        "builds_affected": builds_affected,
    }
    if error:
        payload["error"] = error
    if metrics:
        payload["metrics"] = metrics

    return publish_event("SCAN_UPDATE", payload)


def publish_ingestion_build_update(
    repo_id: str,
    resource: str,
    status: str,
    builds_affected: int = 0,
    chunk_index: int = 0,
    total_chunks: int = 1,
    pipeline_type: str = "",  # "model" or "dataset"
    # For git_worktree - separate completed/failed commits
    completed_commit_shas: Optional[List[str]] = None,
    failed_commit_shas: Optional[List[str]] = None,
    # For build_logs - separate completed/failed build ids
    completed_build_ids: Optional[List[str]] = None,
    failed_build_ids: Optional[List[str]] = None,
) -> bool:
    """
    Publish ingestion build update for real-time per-resource status updates.

    Args:
        repo_id: Repository ID (ModelRepoConfig._id) or Version ID (DatasetVersion._id)
        resource: Resource type (git_history, git_worktree, build_logs)
        status: Overall status (in_progress, completed, failed, completed_with_errors)
        builds_affected: Number of builds successfully affected
        chunk_index: Current chunk index (for chunked operations)
        total_chunks: Total number of chunks
        pipeline_type: "model" or "dataset" to identify the pipeline
        completed_commit_shas: Commits that succeeded (for git_worktree)
        failed_commit_shas: Commits that failed (for git_worktree)
        completed_build_ids: Builds that succeeded (for build_logs)
        failed_build_ids: Builds that failed (for build_logs)

    Returns:
        True if published successfully, False otherwise
    """
    payload = {
        "repo_id": repo_id,
        "resource": resource,
        "status": status,
        "builds_affected": builds_affected,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "pipeline_type": pipeline_type,
    }

    # Git worktree: completed/failed commit shas
    if completed_commit_shas:
        payload["completed_commit_shas"] = completed_commit_shas
    if failed_commit_shas:
        payload["failed_commit_shas"] = failed_commit_shas

    # Build logs: completed/failed build ids
    if completed_build_ids:
        payload["completed_build_ids"] = completed_build_ids
    if failed_build_ids:
        payload["failed_build_ids"] = failed_build_ids

    return publish_event("INGESTION_BUILD_UPDATE", payload)


def publish_ingestion_error(
    raw_repo_id: str,
    resource: str,
    chunk_index: int = 0,
    error: str = "",
    correlation_id: Optional[str] = None,
) -> bool:
    """
    Publish ingestion error event for real-time UI notifications.

    Args:
        raw_repo_id: Repository ID
        resource: Resource type that failed (build_logs, git_worktree, etc.)
        chunk_index: Index of the chunk that failed
        error: Error message
        correlation_id: Correlation ID for tracing

    Returns:
        True if published successfully, False otherwise
    """
    payload = {
        "repo_id": raw_repo_id,
        "resource": resource,
        "chunk_index": chunk_index,
        "error": error,
        "correlation_id": correlation_id,
    }
    return publish_event("INGESTION_ERROR", payload)


def publish_scan_error(
    version_id: str,
    scan_id: str,
    commit_sha: str,
    tool_type: str,
    error: str,
    retry_count: int = 0,
) -> bool:
    """
    Publish scan error event for real-time UI notifications.

    Args:
        version_id: DatasetVersion ID
        scan_id: TrivyCommitScan or SonarCommitScan ID
        commit_sha: The commit SHA that failed scanning
        tool_type: "trivy" or "sonarqube"
        error: Error message
        retry_count: Number of retries attempted

    Returns:
        True if published successfully, False otherwise
    """
    payload = {
        "version_id": version_id,
        "scan_id": scan_id,
        "commit_sha": commit_sha,
        "tool_type": tool_type,
        "error": error,
        "retry_count": retry_count,
    }
    return publish_event("SCAN_ERROR", payload)
