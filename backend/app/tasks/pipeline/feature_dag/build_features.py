"""
Build/workflow related features.

Features extracted from CI workflow run metadata:
- Build ID, number, status, duration
- Source languages
"""

import logging
from typing import List, Optional

from hamilton.function_modifiers import tag

from app.tasks.pipeline.feature_dag._inputs import (
    BuildRunInput,
    FeatureConfigInput,
    GitHubClientInput,
    RepoInput,
)
from app.tasks.pipeline.feature_dag._metadata import (
    FeatureCategory,
    FeatureDataType,
    FeatureResource,
    OutputFormat,
    feature_metadata,
    requires_config,
)

logger = logging.getLogger(__name__)


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
    return int(build_run.ci_run_id)


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
@requires_config(
    source_languages={
        "type": "list",
        "scope": "repo",
        "required": False,
        "description": "Programming languages used in the repository",
        "default": [],
    }
)
def tr_log_lan_all(feature_config: FeatureConfigInput) -> List[str]:
    """All source languages for the repository."""
    return feature_config.get("source_languages", [], scope="repo")


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
    required_resources=[FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def ci_provider(build_run: BuildRunInput) -> str:
    """CI/CD provider name."""
    return build_run.ci_provider


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
    event = payload.get("event", "")
    return event in ("pull_request", "pull_request_target")


def _find_primary_pr(payload: dict) -> Optional[dict]:
    """
    Find the PR that was merged INTO this repo (not fork PRs).

    Fork PRs have base.repo.id != repository.id (they merge FROM upstream TO fork).
    Primary PR has base.repo.id == repository.id (merges INTO this repo).
    """
    pull_requests = payload.get("pull_requests", [])
    repository = payload.get("repository", {})
    repo_id = repository.get("id")
    event = payload.get("event", "unknown")

    if not pull_requests:
        logger.debug(f"No pull_requests in payload (event={event})")
        return None

    if not repo_id:
        logger.warning("Cannot find primary PR: repository.id missing from payload")
        return None

    logger.debug(
        f"Searching for primary PR among {len(pull_requests)} PRs "
        f"(event={event}, repo_id={repo_id})"
    )

    for pr in pull_requests:
        pr_number = pr.get("number")
        base_repo_id = pr.get("base", {}).get("repo", {}).get("id")
        base_repo_name = pr.get("base", {}).get("repo", {}).get("name", "?")

        if base_repo_id == repo_id:
            logger.info(f"Found primary PR #{pr_number} (base.repo.id matches repository.id)")
            return pr
        else:
            logger.debug(
                f"Skipping PR #{pr_number}: base.repo={base_repo_name} "
                f"(id={base_repo_id}) != repo_id={repo_id}"
            )

    logger.debug(f"No primary PR found among {len(pull_requests)} PRs (all are fork PRs)")
    return None


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
    primary_pr = _find_primary_pr(payload)
    if primary_pr:
        return primary_pr.get("number")
    return None


@feature_metadata(
    display_name="PR Created At",
    description="Timestamp when the pull request was created",
    category=FeatureCategory.PR_INFO,
    data_type=FeatureDataType.DATETIME,
    required_resources=[FeatureResource.GITHUB_API, FeatureResource.BUILD_RUN],
)
@tag(group="metadata")
def gh_pr_created_at(
    build_run: BuildRunInput,
    github_client: GitHubClientInput,
) -> Optional[str]:
    """Pull request creation timestamp fetched from GitHub API."""
    payload = build_run.raw_data
    primary_pr = _find_primary_pr(payload)

    if not primary_pr:
        return None

    pr_number = primary_pr.get("number")
    if not pr_number:
        return None

    try:
        full_name = github_client.full_name
        logger.debug(f"Fetching PR #{pr_number} details from GitHub API for {full_name}")
        pr_details = github_client.client.get_pull_request(full_name, pr_number)
        created_at = pr_details.get("created_at")
        logger.debug(f"PR #{pr_number} created_at: {created_at}")
        return created_at
    except Exception as e:
        logger.warning(f"Failed to fetch PR #{pr_number} details: {e}")
        return None
