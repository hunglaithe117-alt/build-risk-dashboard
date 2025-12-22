"""
Ingestion Tracker - Track and log ingestion workflow progress.

This module provides structured logging and status tracking for ingestion workflows.
Supports both model_ingestion and dataset enrichment pipelines.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

import redis

from app.config import settings

logger = logging.getLogger(__name__)


class IngestionStage(str, Enum):
    """Stages in the ingestion workflow."""

    STARTED = "started"
    CLONE = "clone"
    WORKTREE = "worktree"
    LOGS = "logs"
    AGGREGATING = "aggregating"
    DISPATCHING = "dispatching"
    COMPLETED = "completed"
    FAILED = "failed"


class IngestionContext(str, Enum):
    """Context/pipeline type for ingestion."""

    MODEL_TRAINING = "model_training"
    DATASET_ENRICHMENT = "dataset_enrichment"


@dataclass
class IngestionProgress:
    """Progress information for a stage."""

    stage: IngestionStage
    current: int = 0
    total: int = 0
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def percentage(self) -> int:
        if self.total == 0:
            return 0
        return min(100, int((self.current / self.total) * 100))


@dataclass
class IngestionEvent:
    """Single event in ingestion workflow."""

    correlation_id: str
    context: IngestionContext
    stage: IngestionStage
    entity_id: str  # raw_repo_id, version_id, repo_config_id
    entity_type: str  # "raw_repo", "version", "repo_config"
    timestamp: datetime
    task_id: Optional[str] = None
    message: str = ""
    progress: Optional[IngestionProgress] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "context": self.context.value,
            "stage": self.stage.value,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id,
            "message": self.message,
            "progress": (
                {
                    "stage": self.progress.stage.value,
                    "current": self.progress.current,
                    "total": self.progress.total,
                    "percentage": self.progress.percentage,
                    "details": self.progress.details,
                }
                if self.progress
                else None
            ),
            "metadata": self.metadata,
            "error": self.error,
        }


class IngestionTracker:
    """
    Track ingestion workflow progress with structured logging and Redis publishing.

    Usage:
        tracker = IngestionTracker(
            context=IngestionContext.MODEL_TRAINING,
            entity_id=repo_config_id,
            entity_type="repo_config",
            correlation_id=correlation_id,  # Optional, will generate if not provided
        )

        tracker.start(message="Starting ingestion", metadata={"builds": 100})
        tracker.update_stage(IngestionStage.CLONE, message="Cloning repository")
        tracker.update_progress(current=50, total=100)
        tracker.complete(message="Ingestion completed")
    """

    def __init__(
        self,
        context: IngestionContext,
        entity_id: str,
        entity_type: str,
        correlation_id: Optional[str] = None,
        task_id: Optional[str] = None,
        publish_events: bool = True,
    ):
        self.context = context
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.correlation_id = correlation_id or str(uuid4())
        self.task_id = task_id
        self.publish_events = publish_events
        self._current_stage = IngestionStage.STARTED
        self._progress: Optional[IngestionProgress] = None
        self._events: List[IngestionEvent] = []
        self._redis_client: Optional[redis.Redis] = None

    @property
    def log_prefix(self) -> str:
        """Standard log prefix for consistent formatting."""
        return (
            f"[{self.context.value}][{self.entity_type}={self.entity_id}]"
            f"[corr={self.correlation_id[:8]}]"
        )

    def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None:
            try:
                self._redis_client = redis.from_url(settings.REDIS_URL)
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}")
        return self._redis_client

    def _create_event(
        self,
        stage: IngestionStage,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> IngestionEvent:
        """Create an ingestion event."""
        event = IngestionEvent(
            correlation_id=self.correlation_id,
            context=self.context,
            stage=stage,
            entity_id=self.entity_id,
            entity_type=self.entity_type,
            timestamp=datetime.now(timezone.utc),
            task_id=self.task_id,
            message=message,
            progress=self._progress,
            metadata=metadata or {},
            error=error,
        )
        self._events.append(event)
        return event

    def _publish_event(self, event: IngestionEvent) -> None:
        """Publish event to Redis for real-time updates."""
        if not self.publish_events:
            return

        try:
            redis_client = self._get_redis()
            if redis_client:
                redis_client.publish(
                    "ingestion_events",
                    json.dumps(
                        {
                            "type": "INGESTION_UPDATE",
                            "payload": event.to_dict(),
                        }
                    ),
                )
        except Exception as e:
            logger.debug(f"Failed to publish ingestion event: {e}")

    def _log_event(self, event: IngestionEvent, level: int = logging.INFO) -> None:
        """Log the event with structured format."""
        log_msg = f"{self.log_prefix}[{event.stage.value}] {event.message}"

        if event.progress:
            log_msg += f" (progress: {event.progress.current}/{event.progress.total})"

        if event.metadata:
            # Filter out large data for logging
            safe_metadata = {
                k: v
                for k, v in event.metadata.items()
                if not isinstance(v, (list, dict)) or len(str(v)) < 200
            }
            if safe_metadata:
                log_msg += f" metadata={safe_metadata}"

        if event.error:
            log_msg += f" error={event.error}"
            level = logging.ERROR

        logger.log(level, log_msg)

    def start(
        self,
        message: str = "Ingestion started",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark ingestion as started."""
        self._current_stage = IngestionStage.STARTED
        event = self._create_event(IngestionStage.STARTED, message, metadata)
        self._log_event(event)
        self._publish_event(event)

    def update_stage(
        self,
        stage: IngestionStage,
        message: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update to a new stage."""
        self._current_stage = stage
        event = self._create_event(stage, message or f"Entering {stage.value} stage", metadata)
        self._log_event(event)
        self._publish_event(event)

    def update_progress(
        self,
        current: int,
        total: int,
        message: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update progress within current stage."""
        self._progress = IngestionProgress(
            stage=self._current_stage,
            current=current,
            total=total,
            details=details or {},
        )
        event = self._create_event(
            self._current_stage,
            message or f"Progress: {current}/{total}",
        )
        self._log_event(event)
        self._publish_event(event)

    def log_chunk_result(
        self,
        chunk_index: int,
        total_chunks: int,
        result: Dict[str, Any],
        stage: IngestionStage,
    ) -> None:
        """Log result of a chunk task."""
        self._current_stage = stage
        self._progress = IngestionProgress(
            stage=stage,
            current=chunk_index + 1,
            total=total_chunks,
            details=result,
        )
        event = self._create_event(
            stage,
            f"Chunk {chunk_index + 1}/{total_chunks} completed",
            metadata=result,
        )
        self._log_event(event)
        self._publish_event(event)

    def complete(
        self,
        message: str = "Ingestion completed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark ingestion as completed."""
        self._current_stage = IngestionStage.COMPLETED
        event = self._create_event(IngestionStage.COMPLETED, message, metadata)
        self._log_event(event)
        self._publish_event(event)

    def fail(
        self,
        error: str,
        message: str = "Ingestion failed",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mark ingestion as failed."""
        self._current_stage = IngestionStage.FAILED
        event = self._create_event(IngestionStage.FAILED, message, metadata, error=error)
        self._log_event(event, level=logging.ERROR)
        self._publish_event(event)

    def get_events(self) -> List[Dict[str, Any]]:
        """Get all events as dicts."""
        return [e.to_dict() for e in self._events]


def create_tracker_for_model(
    repo_config_id: str,
    task_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> IngestionTracker:
    """Create a tracker for model training ingestion."""
    return IngestionTracker(
        context=IngestionContext.MODEL_TRAINING,
        entity_id=repo_config_id,
        entity_type="repo_config",
        correlation_id=correlation_id,
        task_id=task_id,
    )


def create_tracker_for_enrichment(
    version_id: str,
    task_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> IngestionTracker:
    """Create a tracker for dataset enrichment."""
    return IngestionTracker(
        context=IngestionContext.DATASET_ENRICHMENT,
        entity_id=version_id,
        entity_type="version",
        correlation_id=correlation_id,
        task_id=task_id,
    )


def create_tracker_for_repo(
    raw_repo_id: str,
    context: IngestionContext,
    task_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> IngestionTracker:
    """Create a tracker for a specific repository ingestion."""
    return IngestionTracker(
        context=context,
        entity_id=raw_repo_id,
        entity_type="raw_repo",
        correlation_id=correlation_id,
        task_id=task_id,
    )
