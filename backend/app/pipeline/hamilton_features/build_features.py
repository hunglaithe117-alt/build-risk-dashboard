"""
Build/workflow related features.

Features extracted from CI workflow run metadata:
- Build ID, number, status, duration
- Source languages
"""

from typing import List, Optional

from hamilton.function_modifiers import tag

from app.pipeline.hamilton_features._inputs import RepoInput, WorkflowRunInput
from app.pipeline.hamilton_features._metadata import (
    feature_metadata,
    FeatureCategory,
    FeatureDataType,
)


@feature_metadata(
    display_name="Build ID",
    description="Unique identifier for the CI/CD workflow run",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.INTEGER,
)
@tag(group="build_log")
def tr_build_id(workflow_run: WorkflowRunInput) -> int:
    """Workflow run ID."""
    return workflow_run.workflow_run_id


@feature_metadata(
    display_name="Build Number",
    description="Sequential run number within the workflow",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.INTEGER,
)
@tag(group="build_log")
def tr_build_number(workflow_run: WorkflowRunInput) -> int:
    """Workflow run number."""
    return workflow_run.run_number


@feature_metadata(
    display_name="Commit SHA",
    description="Git commit hash that triggered this build",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.STRING,
)
@tag(group="build_log")
def tr_original_commit(workflow_run: WorkflowRunInput) -> str:
    """Original commit SHA that triggered the build."""
    return workflow_run.head_sha


@feature_metadata(
    display_name="Build Status",
    description="Final status of the build (passed, failed, cancelled, unknown)",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.STRING,
    nullable=False,
)
@tag(group="build_log")
def tr_status(workflow_run: WorkflowRunInput) -> str:
    """
    Normalized build status.

    Maps workflow conclusion to standard status values:
    - failure -> failed
    - success -> passed
    - cancelled -> cancelled
    - other -> as-is or unknown
    """
    conclusion = workflow_run.conclusion
    if not conclusion:
        return "unknown"
    if conclusion == "failure":
        return "failed"
    if conclusion == "success":
        return "passed"
    if conclusion == "cancelled":
        return "cancelled"
    return conclusion


@feature_metadata(
    display_name="Build Duration",
    description="Total time taken for the build to complete",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.FLOAT,
    unit="seconds",
    nullable=False,
)
@tag(group="build_log")
def tr_duration(workflow_run: WorkflowRunInput) -> float:
    """
    Build duration in seconds.

    Calculated from workflow created_at to updated_at timestamps.
    """
    if workflow_run.ci_created_at and workflow_run.ci_updated_at:
        delta = workflow_run.ci_updated_at - workflow_run.ci_created_at
        return delta.total_seconds()
    return 0.0


@feature_metadata(
    display_name="Source Languages",
    description="Programming languages used in the repository",
    category=FeatureCategory.REPO_SNAPSHOT,
    data_type=FeatureDataType.LIST_STRING,
)
@tag(group="build_log")
def tr_log_lan_all(repo: RepoInput) -> List[str]:
    """All source languages for the repository."""
    return repo.source_languages


@feature_metadata(
    display_name="Project Name",
    description="Full repository name (owner/repo)",
    category=FeatureCategory.METADATA,
    data_type=FeatureDataType.STRING,
    nullable=False,
)
@tag(group="metadata")
def gh_project_name(repo: RepoInput) -> str:
    """Full repository name (owner/repo)."""
    return repo.full_name


@feature_metadata(
    display_name="Main Language",
    description="Primary programming language of the repository",
    category=FeatureCategory.REPO_SNAPSHOT,
    data_type=FeatureDataType.STRING,
)
@tag(group="metadata")
def gh_lang(repo: RepoInput) -> Optional[str]:
    """Primary programming language."""
    return repo.main_lang


@feature_metadata(
    display_name="CI Provider",
    description="CI/CD provider name (e.g., GitHub Actions, Travis CI)",
    category=FeatureCategory.METADATA,
    data_type=FeatureDataType.STRING,
)
@tag(group="metadata")
def ci_provider(repo: RepoInput) -> str:
    """CI/CD provider name."""
    return repo.ci_provider


@feature_metadata(
    display_name="Build Trigger Commit",
    description="Commit SHA that triggered the build",
    category=FeatureCategory.METADATA,
    data_type=FeatureDataType.STRING,
)
@tag(group="metadata")
def git_trigger_commit(workflow_run: WorkflowRunInput) -> str:
    """Commit SHA that triggered the build."""
    return workflow_run.head_sha


@feature_metadata(
    display_name="Build Started At",
    description="Build start timestamp in ISO format",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.DATETIME,
)
@tag(group="metadata")
def gh_build_started_at(workflow_run: WorkflowRunInput) -> Optional[str]:
    """Build start timestamp in ISO format."""
    if workflow_run.ci_created_at:
        return workflow_run.ci_created_at.isoformat()
    return None


@feature_metadata(
    display_name="Git Branch",
    description="Branch name from workflow run payload",
    category=FeatureCategory.GIT_HISTORY,
    data_type=FeatureDataType.STRING,
)
@tag(group="metadata")
def git_branch(workflow_run: WorkflowRunInput) -> Optional[str]:
    """Branch name from workflow run payload."""
    return workflow_run.raw_payload.get("head_branch")


@feature_metadata(
    display_name="Is Pull Request",
    description="Whether this build was triggered by a pull request",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.BOOLEAN,
    nullable=False,
)
@tag(group="metadata")
def gh_is_pr(workflow_run: WorkflowRunInput) -> bool:
    """Whether this build is triggered by a pull request."""
    payload = workflow_run.raw_payload
    pull_requests = payload.get("pull_requests", [])
    return len(pull_requests) > 0 or payload.get("event") == "pull_request"


@feature_metadata(
    display_name="PR Number",
    description="Pull request number if applicable",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.INTEGER,
)
@tag(group="metadata")
def gh_pull_req_num(workflow_run: WorkflowRunInput) -> Optional[int]:
    """Pull request number if this build is PR-triggered."""
    payload = workflow_run.raw_payload
    pull_requests = payload.get("pull_requests", [])
    if pull_requests:
        return pull_requests[0].get("number")
    return None


@feature_metadata(
    display_name="PR Created At",
    description="Timestamp when the pull request was created",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.DATETIME,
)
@tag(group="metadata")
def gh_pr_created_at(workflow_run: WorkflowRunInput) -> Optional[str]:
    """Pull request creation timestamp if available."""
    payload = workflow_run.raw_payload
    pull_requests = payload.get("pull_requests", [])
    if pull_requests:
        return pull_requests[0].get("created_at")
    return None
