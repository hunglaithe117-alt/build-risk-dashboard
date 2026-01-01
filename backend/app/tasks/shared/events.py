"""
Shared event publishing utilities for real-time WebSocket updates.

This module provides functions to publish events to Redis pub/sub,
which are then forwarded to WebSocket clients by the API layer.
"""

import json
import logging
from typing import Any, Dict, Optional

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
        redis_client.publish(EVENTS_CHANNEL, message)
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
