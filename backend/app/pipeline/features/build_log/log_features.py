"""
Build Log Feature Nodes.

Extracts features from CI build logs:
- Test results (run, passed, failed, skipped)
- Test duration
- Frameworks detected
- Job information
"""

from typing import Any, Dict, List, Set

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.log_storage import LogStorageHandle
from app.services.extracts.log_parser import TestLogParser


@register_feature(
    name="build_log_features",
    requires_resources={ResourceNames.LOG_STORAGE, ResourceNames.WORKFLOW_RUN},
    provides={
        "tr_jobs",
        "tr_build_id", 
        "tr_build_number",
        "tr_original_commit",
        "tr_log_lan_all",
        "tr_log_frameworks_all",
        "tr_log_num_jobs",
        "tr_log_tests_run_sum",
        "tr_log_tests_failed_sum",
        "tr_log_tests_skipped_sum",
        "tr_log_tests_ok_sum",
        "tr_log_tests_fail_rate",
        "tr_log_testduration_sum",
        "tr_status",
        "tr_duration",
    },
    group="build_log",
)
class BuildLogFeaturesNode(FeatureNode):
    """Extracts test and build metrics from CI logs."""
    
    def __init__(self):
        self.parser = TestLogParser()
    
    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        log_storage: LogStorageHandle = context.get_resource(ResourceNames.LOG_STORAGE)
        workflow_run = context.workflow_run
        repo = context.repo
        
        if not log_storage.has_logs:
            return self._empty_result(workflow_run, repo)
        
        # Aggregators
        tr_jobs: List[int] = []
        frameworks: Set[str] = set()
        total_jobs = 0
        tests_run_sum = 0
        tests_failed_sum = 0
        tests_skipped_sum = 0
        tests_ok_sum = 0
        test_duration_sum = 0.0
        
        for log_file in log_storage.log_files:
            try:
                tr_jobs.append(log_file.job_id)
                total_jobs += 1
                
                content = log_file.read()
                parsed = self.parser.parse(content)
                
                if parsed.framework:
                    frameworks.add(parsed.framework)
                
                tests_run_sum += parsed.tests_run
                tests_failed_sum += parsed.tests_failed
                tests_skipped_sum += parsed.tests_skipped
                tests_ok_sum += parsed.tests_ok
                
                if parsed.test_duration_seconds:
                    test_duration_sum += parsed.test_duration_seconds
                    
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to parse log {log_file.path}: {e}")
        
        # Derived metrics
        fail_rate = tests_failed_sum / tests_run_sum if tests_run_sum > 0 else 0.0
        
        # Determine status
        tr_status = "passed"
        if workflow_run.conclusion == "failure":
            tr_status = "failed"
        elif workflow_run.conclusion == "cancelled":
            tr_status = "cancelled"
        elif tests_failed_sum > 0:
            tr_status = "failed"
        
        # Duration
        tr_duration = 0.0
        if workflow_run.created_at and workflow_run.updated_at:
            delta = workflow_run.updated_at - workflow_run.created_at
            tr_duration = delta.total_seconds()
        
        return {
            "tr_jobs": tr_jobs,
            "tr_build_id": workflow_run.workflow_run_id,
            "tr_build_number": workflow_run.run_number,
            "tr_original_commit": workflow_run.head_sha,
            "tr_log_lan_all": [lang.value if hasattr(lang, 'value') else lang for lang in repo.source_languages],
            "tr_log_frameworks_all": list(frameworks),
            "tr_log_num_jobs": total_jobs,
            "tr_log_tests_run_sum": tests_run_sum,
            "tr_log_tests_failed_sum": tests_failed_sum,
            "tr_log_tests_skipped_sum": tests_skipped_sum,
            "tr_log_tests_ok_sum": tests_ok_sum,
            "tr_log_tests_fail_rate": fail_rate,
            "tr_log_testduration_sum": test_duration_sum,
            "tr_status": tr_status,
            "tr_duration": tr_duration,
        }
    
    def _empty_result(self, workflow_run, repo) -> Dict[str, Any]:
        """Return empty features when no logs are available."""
        return {
            "tr_jobs": [],
            "tr_build_id": workflow_run.workflow_run_id if workflow_run else None,
            "tr_build_number": workflow_run.run_number if workflow_run else None,
            "tr_original_commit": workflow_run.head_sha if workflow_run else None,
            "tr_log_lan_all": [lang.value if hasattr(lang, 'value') else lang for lang in repo.source_languages] if repo else [],
            "tr_log_frameworks_all": [],
            "tr_log_num_jobs": 0,
            "tr_log_tests_run_sum": 0,
            "tr_log_tests_failed_sum": 0,
            "tr_log_tests_skipped_sum": 0,
            "tr_log_tests_ok_sum": 0,
            "tr_log_tests_fail_rate": 0.0,
            "tr_log_testduration_sum": 0.0,
            "tr_status": "unknown",
            "tr_duration": 0.0,
        }
