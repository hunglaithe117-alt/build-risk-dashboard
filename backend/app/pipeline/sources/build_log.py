"""
Build Log Data Source - Provides features from CI build logs.

Features provided:
- Job metadata (duration, status, runner)
- Test results parsing (passed, failed, skipped)
- Workflow metadata
"""

from typing import List, Set

from app.pipeline.sources import (
    DataSource,
    DataSourceConfig,
    DataSourceMetadata,
    DataSourceType,
    register_data_source,
)
from app.pipeline.core.context import ExecutionContext


@register_data_source(DataSourceType.BUILD_LOG)
class BuildLogDataSource(DataSource):
    """
    CI Build Log data source.

    Fetches and parses CI build logs to extract test results
    and job metadata.
    """

    @classmethod
    def get_metadata(cls) -> DataSourceMetadata:
        return DataSourceMetadata(
            source_type=DataSourceType.BUILD_LOG,
            display_name="Build Logs",
            description="Fetch and parse CI build logs for test results and job metadata",
            icon="file-text",
            requires_config=False,
            config_fields=[
                {
                    "name": "fetch_logs",
                    "type": "boolean",
                    "label": "Download full logs",
                    "description": "Download complete build logs (slower but more data)",
                    "default": True,
                },
            ],
            features_provided=cls.get_feature_names(),
            resource_dependencies={"log_storage", "workflow_run"},
        )

    @classmethod
    def get_feature_names(cls) -> Set[str]:
        """All features provided by build log feature nodes."""
        return {
            # From job_metadata.py
            "tr_job_ids",
            "tr_job_names",
            "tr_build_duration_ms",
            "tr_jobs_count",
            # From workflow_metadata.py
            "tr_workflow_name",
            "tr_event_type",
            "tr_head_branch",
            "tr_started_at",
            "tr_trigger_actor",
            "tr_run_attempt",
            "tr_is_retry",
            # From test_log_parser.py
            "tr_tests_passed",
            "tr_tests_failed",
            "tr_tests_skipped",
            "tr_tests_errored",
            "tr_test_duration_ms",
            "tr_test_suites_count",
            "tr_test_pass_rate",
            "tr_test_frameworks",
            "tr_failed_test_names",
            "tr_has_test_results",
        }

    @classmethod
    def get_required_resources(cls) -> Set[str]:
        return {"log_storage", "workflow_run"}

    @classmethod
    def is_available(cls, context: ExecutionContext) -> bool:
        return context.has_resource("workflow_run")

    @classmethod
    def validate_config(cls, config: DataSourceConfig) -> List[str]:
        errors = []
        # No mandatory config for build logs
        return errors
