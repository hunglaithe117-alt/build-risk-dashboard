"""
Build/workflow related features.

Features extracted from CI workflow run metadata:
- Build ID, number, status, duration
- Source languages
"""

from typing import List, Optional

from hamilton.function_modifiers import tag

from app.tasks.pipeline.feature_dag._inputs import (
    RepoInput,
    BuildRunInput,
    RepoConfigInput,
)
from app.tasks.pipeline.feature_dag._metadata import (
    feature_metadata,
    FeatureCategory,
    FeatureDataType,
    FeatureResource,
    OutputFormat,
)


@feature_metadata(
    display_name="Build ID",
    description="Unique identifier for the CI/CD workflow run",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.INTEGER,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="build_log")
def tr_build_id(build_run: BuildRunInput) -> int:
    """Workflow run ID."""
    return int(build_run.build_id)


@feature_metadata(
    display_name="Build Number",
    description="Sequential run number within the workflow",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.INTEGER,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="build_log")
def tr_build_number(build_run: BuildRunInput) -> int:
    """Workflow run number."""
    return build_run.build_number or 0


@feature_metadata(
    display_name="Commit SHA",
    description="Git commit hash that triggered this build",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.STRING,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="build_log")
def tr_original_commit(build_run: BuildRunInput) -> str:
    """Original commit SHA that triggered the build."""
    return build_run.commit_sha


@feature_metadata(
    display_name="Build Status",
    description="Final status of the build (passed, failed, cancelled, unknown)",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.STRING,
    required_resources=[FeatureResource.BUILD_RUN],
    nullable=False,
)
@tag(group="build_log")
def tr_status(build_run: BuildRunInput) -> str:
    """
    Normalized build status.

    Maps workflow conclusion to standard status values:
    - failure -> failed
    - success -> passed
    - cancelled -> cancelled
    - errored -> errored
    - other -> as-is or unknown
    """
    conclusion = build_run.conclusion
    if not conclusion:
        return "unknown"

    status_map = {
        "failure": "failed",
        "success": "passed",
        "cancelled": "cancelled",
        "errored": "errored",
        "timed_out": "errored",
        "action_required": "errored",
    }
    return status_map.get(conclusion, conclusion)


@feature_metadata(
    display_name="Build Duration",
    description="Total time taken for the build to complete",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.FLOAT,
    required_resources=[FeatureResource.BUILD_RUN],
    unit="seconds",
    nullable=False,
)
@tag(group="build_log")
def tr_duration(build_run: BuildRunInput) -> float:
    """
    Build duration in seconds.

    Uses duration_seconds from CI API if available (preferred),
    otherwise calculates from created_at to completed_at timestamps.
    """
    # Prefer API-provided duration (matches TravisTorrent behavior)
    if build_run.duration_seconds is not None:
        return build_run.duration_seconds

    # Fallback: calculate from timestamps
    if build_run.created_at and build_run.completed_at:
        delta = build_run.completed_at - build_run.created_at
        return delta.total_seconds()
    return 0.0


@feature_metadata(
    display_name="Source Languages",
    description="Programming languages used in the repository",
    category=FeatureCategory.REPO_SNAPSHOT,
    data_type=FeatureDataType.LIST_STRING,
    required_resources=[FeatureResource.REPO],
    output_format=OutputFormat.COMMA_SEPARATED,
)
@tag(group="build_log")
def tr_log_lan_all(repo: RepoConfigInput) -> List[str]:
    """All source languages for the repository."""
    return repo.source_languages


@feature_metadata(
    display_name="Project Name",
    description="Full repository name (owner/repo)",
    category=FeatureCategory.METADATA,
    data_type=FeatureDataType.STRING,
    required_resources=[FeatureResource.REPO],
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
    required_resources=[FeatureResource.REPO],
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
    required_resources=[FeatureResource.REPO_CONFIG],
)
@tag(group="metadata")
def ci_provider(repo_config: RepoConfigInput) -> str:
    """CI/CD provider name."""
    return repo_config.ci_provider


@feature_metadata(
    display_name="Build Trigger Commit",
    description="Commit SHA that triggered the build",
    category=FeatureCategory.METADATA,
    data_type=FeatureDataType.STRING,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def git_trigger_commit(build_run: BuildRunInput) -> str:
    """Commit SHA that triggered the build."""
    return build_run.commit_sha


@feature_metadata(
    display_name="Build Started At",
    description="Build start timestamp in ISO format",
    category=FeatureCategory.WORKFLOW,
    data_type=FeatureDataType.DATETIME,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def gh_build_started_at(build_run: BuildRunInput) -> Optional[str]:
    """Build start timestamp in ISO format."""
    if build_run.created_at:
        return build_run.created_at.isoformat()
    return None


@feature_metadata(
    display_name="Git Branch",
    description="Branch name from workflow run payload",
    category=FeatureCategory.GIT_HISTORY,
    data_type=FeatureDataType.STRING,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def git_branch(build_run: BuildRunInput) -> Optional[str]:
    """Branch name from workflow run payload."""
    return build_run.raw_data.get("head_branch")


@feature_metadata(
    display_name="Is Pull Request",
    description="Whether this build was triggered by a pull request",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.BOOLEAN,
    required_resources=[FeatureResource.BUILD_RUN],
    nullable=False,
)
@tag(group="metadata")
def gh_is_pr(build_run: BuildRunInput) -> bool:
    """Whether this build is triggered by a pull request."""
    payload = build_run.raw_data
    pull_requests = payload.get("pull_requests", [])
    return len(pull_requests) > 0 or payload.get("event") == "pull_request"


@feature_metadata(
    display_name="PR Number",
    description="Pull request number if applicable",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.INTEGER,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def gh_pull_req_num(build_run: BuildRunInput) -> Optional[int]:
    """Pull request number if this build is PR-triggered."""
    payload = build_run.raw_data
    pull_requests = payload.get("pull_requests", [])
    if pull_requests:
        return pull_requests[0].get("number")
    return None


@feature_metadata(
    display_name="PR Created At",
    description="Timestamp when the pull request was created",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.DATETIME,
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def gh_pr_created_at(build_run: BuildRunInput) -> Optional[str]:
    """Pull request creation timestamp if available."""
    payload = build_run.raw_data
    pull_requests = payload.get("pull_requests", [])
    if pull_requests:
        return pull_requests[0].get("created_at")
    return None
