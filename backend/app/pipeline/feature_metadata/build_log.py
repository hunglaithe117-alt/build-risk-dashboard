"""
Build Log Feature Metadata.

Centralized metadata definitions for all build_log features:
- job_metadata: tr_jobs, tr_log_num_jobs
- test_log_parser: tr_log_frameworks_all, tr_log_tests_*, tr_log_testduration_sum
- workflow_metadata: tr_build_id, tr_status, tr_duration, etc.
"""

from app.pipeline.core.registry import (
    FeatureMetadata,
    FeatureCategory,
    FeatureDataType,
    FeatureSource,
)

JOB_METADATA = {
    "tr_log_num_jobs": FeatureMetadata(
        display_name="Build Job Count",
        description="The number of build jobs in this CI run",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="3",
    ),
    "tr_jobs": FeatureMetadata(
        display_name="Job IDs",
        description="List of all job IDs in this build run",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.LIST_INTEGER,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="[12345, 12346, 12347]",
    ),
}

TEST_LOG_PARSER = {
    "tr_log_frameworks_all": FeatureMetadata(
        display_name="Test Frameworks",
        description="List of test frameworks detected in build logs (e.g., pytest, jest, rspec)",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.LIST_STRING,
        source=FeatureSource.BUILD_LOG,
        example_value="pytest,unittest",
    ),
    "tr_log_tests_run_sum": FeatureMetadata(
        display_name="Tests Run",
        description="Total number of test cases executed across all jobs",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="156",
    ),
    "tr_log_tests_failed_sum": FeatureMetadata(
        display_name="Tests Failed",
        description="Total number of test cases that failed",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="3",
    ),
    "tr_log_tests_skipped_sum": FeatureMetadata(
        display_name="Tests Skipped",
        description="Total number of test cases that were skipped",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="5",
    ),
    "tr_log_tests_ok_sum": FeatureMetadata(
        display_name="Tests Passed",
        description="Total number of test cases that passed",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="148",
    ),
    "tr_log_tests_fail_rate": FeatureMetadata(
        display_name="Test Failure Rate",
        description="Ratio of failed tests to total tests run (0.0 to 1.0)",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.FLOAT,
        source=FeatureSource.COMPUTED,
        nullable=False,
        example_value="0.019",
    ),
    "tr_log_testduration_sum": FeatureMetadata(
        display_name="Test Duration",
        description="Total time spent running tests in seconds",
        category=FeatureCategory.BUILD_LOG,
        data_type=FeatureDataType.FLOAT,
        source=FeatureSource.BUILD_LOG,
        nullable=False,
        example_value="45.32",
        unit="seconds",
    ),
}


WORKFLOW_METADATA = {
    "tr_build_id": FeatureMetadata(
        display_name="Build ID",
        description="Unique identifier for the CI/CD workflow run",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.WORKFLOW_RUN,
        example_value="1234567890",
    ),
    "tr_build_number": FeatureMetadata(
        display_name="Build Number",
        description="Sequential run number within the workflow",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.WORKFLOW_RUN,
        example_value="42",
    ),
    "tr_original_commit": FeatureMetadata(
        display_name="Commit SHA",
        description="Git commit hash that triggered this build",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.STRING,
        source=FeatureSource.WORKFLOW_RUN,
        example_value="abc123def456",
    ),
    "tr_status": FeatureMetadata(
        display_name="Build Status",
        description="Final status of the build (passed, failed, cancelled, unknown)",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.STRING,
        source=FeatureSource.WORKFLOW_RUN,
        nullable=False,
        example_value="passed",
    ),
    "tr_duration": FeatureMetadata(
        display_name="Build Duration",
        description="Total time taken for the build to complete",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.FLOAT,
        source=FeatureSource.WORKFLOW_RUN,
        nullable=False,
        example_value="180.5",
        unit="seconds",
    ),
    "tr_log_lan_all": FeatureMetadata(
        display_name="Source Languages",
        description="Programming languages used in the repository",
        category=FeatureCategory.REPO_SNAPSHOT,
        data_type=FeatureDataType.LIST_STRING,
        source=FeatureSource.METADATA,
        example_value="python,javascript",
    ),
}


BUILD_LOG_METADATA = {
    **JOB_METADATA,
    **TEST_LOG_PARSER,
    **WORKFLOW_METADATA,
}
