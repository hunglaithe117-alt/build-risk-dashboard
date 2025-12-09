"""
Job Metadata Node.

Extracts job-level metadata from CI logs:
- tr_jobs (list of job IDs)
- tr_log_num_jobs (count of jobs)
"""

from typing import Any, Dict, List

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.log_storage import LogStorageHandle
from app.pipeline.feature_metadata.build_log import JOB_METADATA


@register_feature(
    name="job_metadata",
    requires_resources={ResourceNames.LOG_STORAGE},
    provides={
        "tr_jobs",
        "tr_log_num_jobs",
    },
    group="build_log",
    priority=8,
    feature_metadata=JOB_METADATA,
)
class JobMetadataNode(FeatureNode):
    """Extracts job IDs and count from log storage."""

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        log_storage: LogStorageHandle = context.get_resource(ResourceNames.LOG_STORAGE)

        if not log_storage.has_logs:
            return {"tr_jobs": [], "tr_log_num_jobs": 0}

        tr_jobs: List[int] = []
        for log_file in log_storage.log_files:
            tr_jobs.append(log_file.job_id)

        return {
            "tr_jobs": tr_jobs,
            "tr_log_num_jobs": len(tr_jobs),
        }
