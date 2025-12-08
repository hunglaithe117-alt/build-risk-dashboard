"""
Workflow Metadata Node.

Extracts cheap metadata from workflow run without parsing logs:
- tr_build_id, tr_build_number, tr_original_commit
- tr_status, tr_duration
- tr_log_lan_all
"""

from typing import Any, Dict

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames


@register_feature(
    name="workflow_metadata",
    requires_resources=set(),
    provides={
        "tr_build_id",
        "tr_build_number",
        "tr_original_commit",
        "tr_status",
        "tr_duration",
        "tr_log_lan_all",
    },
    group="build_log",
    priority=10,  # High priority - metadata is cheap and often needed
)
class WorkflowMetadataNode(FeatureNode):
    """Extracts cheap metadata from workflow run (no log parsing)."""

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        workflow_run = context.workflow_run
        repo = context.repo

        return {
            "tr_build_id": workflow_run.workflow_run_id if workflow_run else None,
            "tr_build_number": workflow_run.run_number if workflow_run else None,
            "tr_original_commit": workflow_run.head_sha if workflow_run else None,
            "tr_status": self._determine_status(workflow_run),
            "tr_duration": self._compute_duration(workflow_run),
            "tr_log_lan_all": self._get_languages(repo),
        }

    def _determine_status(self, workflow_run) -> str:
        """Derive build status from workflow conclusion."""
        if not workflow_run:
            return "unknown"
        if workflow_run.conclusion == "failure":
            return "failed"
        if workflow_run.conclusion == "cancelled":
            return "cancelled"
        if workflow_run.conclusion == "success":
            return "passed"
        return workflow_run.conclusion or "unknown"

    def _compute_duration(self, workflow_run) -> float:
        """Compute build duration from workflow timestamps."""
        if workflow_run and workflow_run.created_at and workflow_run.updated_at:
            delta = workflow_run.updated_at - workflow_run.created_at
            return delta.total_seconds()
        return 0.0

    def _get_languages(self, repo) -> list:
        """Extract source languages from repo metadata."""
        if not repo or not repo.source_languages:
            return []
        return [
            lang.value if hasattr(lang, "value") else lang
            for lang in repo.source_languages
        ]
