"""
Hamilton Execution Tracker - Lifecycle adapter for monitoring DAG execution.

This module provides an ExecutionTracker that hooks into Hamilton's lifecycle
to record timing, success/failure, and errors for each node execution.

Usage:
    tracker = ExecutionTracker()
    driver = Driver(..., adapters=[tracker])
    result = driver.execute(...)
    execution_info = tracker.get_results()
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from hamilton.graph import node
from hamilton.lifecycle import base

logger = logging.getLogger(__name__)


@dataclass
class NodeExecutionInfo:
    """Information about a single node execution."""

    node_name: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    success: bool = True
    error: Optional[str] = None
    skipped: bool = False
    result: Any = None


@dataclass
class ExecutionResult:
    """Summary of pipeline execution."""

    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    nodes_executed: int = 0
    nodes_succeeded: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0
    node_results: List[NodeExecutionInfo] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class ExecutionTracker(base.BasePreNodeExecute, base.BasePostNodeExecute):
    """
    Hamilton lifecycle adapter for tracking node execution.

    Implements pre/post node execution hooks to record:
    - Start/end timestamps for each node
    - Success/failure status
    - Error messages if any
    - Overall execution summary
    """

    def __init__(self):
        """Initialize tracker with empty state."""
        self._node_timings: Dict[str, Dict[str, Any]] = {}
        self._node_results: List[NodeExecutionInfo] = []
        self._errors: List[str] = []
        self._started_at: Optional[datetime] = None
        self._completed_at: Optional[datetime] = None

    def reset(self) -> None:
        """Reset tracker state for reuse."""
        self._node_timings = {}
        self._node_results = []
        self._errors = []
        self._started_at = None
        self._completed_at = None

    def pre_node_execute(
        self,
        *,
        run_id: str,
        node_: node.Node,
        kwargs: Dict[str, Any],
        task_id: Optional[str] = None,
    ) -> None:
        """
        Called before each node execution.

        Records start time for the node.

        Args:
            run_id: Unique run identifier
            node_: Hamilton Node object containing name, tags, return type, etc.
            kwargs: Arguments being passed to the node
            task_id: Optional task identifier
        """
        node_name = node_.name

        if self._started_at is None:
            self._started_at = datetime.now(timezone.utc)

        self._node_timings[node_name] = {
            "start_time": time.perf_counter(),
            "started_at": datetime.now(timezone.utc),
        }

    def post_node_execute(
        self,
        *,
        run_id: str,
        node_: node.Node,
        kwargs: Dict[str, Any],
        success: bool,
        error: Optional[Exception],
        result: Any,
        task_id: Optional[str] = None,
    ) -> None:
        """
        Called after each node execution.

        Records end time, duration, and success/failure status.

        Args:
            run_id: Unique run identifier
            node_: Hamilton Node object containing name, tags, return type, etc.
            kwargs: Arguments that were passed to the node
            success: Whether the node executed successfully
            error: Exception if the node failed
            result: The result of node execution
            task_id: Optional task identifier
        """
        node_name = node_.name
        timing = self._node_timings.get(node_name, {})
        start_time = timing.get("start_time", time.perf_counter())
        started_at = timing.get("started_at", datetime.now(timezone.utc))
        completed_at = datetime.now(timezone.utc)

        duration_ms = (time.perf_counter() - start_time) * 1000

        node_info = NodeExecutionInfo(
            node_name=node_name,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            success=success,
            error=str(error) if error else None,
            skipped=False,
            result=result if success else None,
        )

        self._node_results.append(node_info)

        if error:
            error_msg = f"{node_name}: {error}"
            self._errors.append(error_msg)
            logger.warning(f"Node {node_name} failed: {error}")

        self._completed_at = completed_at

    def get_results(self) -> ExecutionResult:
        """
        Get execution results summary.

        Returns:
            ExecutionResult with timing and status info for all nodes.
        """
        nodes_succeeded = sum(1 for n in self._node_results if n.success)
        nodes_failed = sum(1 for n in self._node_results if not n.success)
        nodes_skipped = sum(1 for n in self._node_results if n.skipped)

        duration_ms = 0.0
        if self._started_at and self._completed_at:
            duration_ms = (self._completed_at - self._started_at).total_seconds() * 1000

        return ExecutionResult(
            started_at=self._started_at,
            completed_at=self._completed_at,
            duration_ms=duration_ms,
            nodes_executed=len(self._node_results),
            nodes_succeeded=nodes_succeeded,
            nodes_failed=nodes_failed,
            nodes_skipped=nodes_skipped,
            node_results=self._node_results.copy(),
            errors=self._errors.copy(),
        )
