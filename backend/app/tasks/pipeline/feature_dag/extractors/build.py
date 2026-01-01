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
from app.tasks.pipeline.feature_dag._metadata import requires_config

logger = logging.getLogger(__name__)


@tag(group="build_log")
def tr_build_id(build_run: BuildRunInput) -> int:
    """Workflow run ID."""
    return int(build_run.ci_run_id)


@tag(group="build_log")
def tr_build_number(build_run: BuildRunInput) -> int:
    """Workflow run number."""
    return build_run.build_number or 0


@tag(group="build_log")
def tr_original_commit(build_run: BuildRunInput) -> str:
    """Original commit SHA that triggered the build."""
    return build_run.commit_sha


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


@tag(group="build_log")
def tr_status_num(tr_status: str) -> int:
    """
    Numeric build status for model input.

    Maps:
    - passed -> 0
    - failed -> 1
    - other -> -1
    """
    status_map = {"passed": 0, "failed": 1}
    return status_map.get(tr_status, -1)


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
    return [lang.lower() for lang in feature_config.get("source_languages", [], scope="repo")] or [
        ""
    ]


@tag(group="metadata")
def gh_project_name(repo: RepoInput) -> str:
    """Full repository name (owner/repo)."""
    return repo.full_name


@tag(group="metadata")
def gh_lang(repo: RepoInput) -> Optional[str]:
    """Primary programming language."""
    return repo.main_lang.lower() if repo.main_lang else None


@tag(group="metadata")
def ci_provider(build_run: BuildRunInput) -> str:
    """CI/CD provider name."""
    return build_run.ci_provider


@tag(group="metadata")
def git_trigger_commit(build_run: BuildRunInput) -> str:
    """
    Commit SHA that triggered the build.

    CI Provider Differences:
    - GitHub Actions: Returns head_sha directly (no virtual commits)
    - Circle CI: Returns commit SHA directly (no virtual commits)
    - Travis CI: For PR builds, Travis creates virtual merge commits.
                 We resolve to actual commit by parsing commit message.

    Returns:
        The actual commit SHA that triggered the build.
    """
    ci_provider = build_run.ci_provider

    # For Travis CI PR builds, resolve virtual merge commit
    if ci_provider == "travis_ci":
        return _resolve_travis_trigger_commit(build_run)

    # For GitHub Actions and Circle CI, commit_sha is the real commit
    return build_run.commit_sha


def _is_pr_build(build_run: BuildRunInput) -> bool:
    """
    Check if build was triggered by a pull request (CI-agnostic).

    Handles different CI providers:
    - GitHub Actions: event == "pull_request" or "pull_request_target"
    - Travis CI: pull_request field is truthy or pull_req is not None
    - Circle CI: pull_requests array is non-empty or branch starts with "pull/"

    Returns:
        True if this build is PR-triggered, False otherwise.
    """
    raw_data = build_run.raw_data
    ci_provider = build_run.ci_provider

    if ci_provider == "github_actions":
        event = raw_data.get("event", "")
        return event in ("pull_request", "pull_request_target")

    elif ci_provider == "travis_ci":
        # Travis uses pull_request (bool) or pull_req (PR number)
        return raw_data.get("pull_request", False) or raw_data.get("pull_req") is not None

    elif ci_provider == "circleci":
        # Circle CI: check for pull_requests array or branch pattern
        pull_requests = raw_data.get("pull_requests", [])
        branch = raw_data.get("branch", "")
        return len(pull_requests) > 0 or branch.startswith("pull/")

    # Fallback: check common fields
    return (
        raw_data.get("pull_request", False)
        or raw_data.get("pull_req") is not None
        or len(raw_data.get("pull_requests", [])) > 0
    )


def _resolve_travis_trigger_commit(build_run: BuildRunInput) -> str:
    """
    Resolve Travis CI virtual merge commit to actual commit.

    When Travis CI builds a PR, it creates a virtual merge commit by merging
    the PR head into the target branch. The commit message looks like:
    "Merge abc123def into main"

    For PR builds, we extract the actual PR commit SHA from this message.
    For non-PR builds, we return the original commit SHA.
    """
    import re

    commit_sha = build_run.commit_sha

    # Use CI-agnostic PR check
    if not _is_pr_build(build_run):
        # Non-PR builds: commit_sha is the real commit
        return commit_sha

    # For PR builds, try to resolve from commit message
    raw_data = build_run.raw_data
    commit_message = raw_data.get("commit_message", "") or raw_data.get("message", "")

    # Match pattern: "Merge abc123 into xyz789" or "Merge abc123 into main"
    match = re.search(r"Merge\s+([a-f0-9]+)\s+into\s+", commit_message, re.IGNORECASE)

    if match:
        actual_sha = match.group(1)
        logger.info(f"Resolved Travis virtual commit {commit_sha[:8]} to actual {actual_sha[:8]}")
        return actual_sha

    # Fallback: return original commit_sha
    logger.debug(f"Could not resolve Travis virtual commit from message: {commit_message[:50]}")
    return commit_sha


@tag(group="metadata")
def gh_build_started_at(build_run: BuildRunInput) -> Optional[str]:
    """Build start timestamp in ISO format."""
    if build_run.created_at:
        return build_run.created_at.isoformat()
    return None


@tag(group="metadata")
def git_branch(build_run: BuildRunInput) -> Optional[str]:
    """Branch name (uses normalized field from RawBuildRun)."""
    return build_run.branch


@tag(group="metadata")
def gh_is_pr(build_run: BuildRunInput) -> bool:
    """Whether this build is triggered by a pull request (works with all CI providers)."""
    return _is_pr_build(build_run)


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


def _get_pr_number(build_run: BuildRunInput) -> Optional[int]:
    """
    Get PR number from build (CI-agnostic).

    CI Provider Differences:
    - GitHub Actions: pull_requests[0].number (uses _find_primary_pr for fork detection)
    - Travis CI: pull_req field
    - Circle CI: extract from vcs.pull_requests[] URLs or branch pattern
    """
    raw_data = build_run.raw_data
    ci_provider = build_run.ci_provider

    if ci_provider == "github_actions":
        primary_pr = _find_primary_pr(raw_data)
        if primary_pr:
            return primary_pr.get("number")
        return None

    elif ci_provider == "travis_ci":
        # Travis stores PR number in pull_req field
        pull_req = raw_data.get("pull_req")
        if pull_req is not None:
            return int(pull_req) if isinstance(pull_req, (int, str)) else None
        return None

    elif ci_provider == "circleci":
        # Circle CI: extract from pull_requests URLs or branch pattern
        vcs = raw_data.get("vcs", {})
        pull_requests = vcs.get("pull_requests", [])
        if pull_requests:
            # URLs look like: https://github.com/owner/repo/pull/123
            url = pull_requests[0] if isinstance(pull_requests[0], str) else None
            if url and "/pull/" in url:
                import re

                match = re.search(r"/pull/(\d+)", url)
                if match:
                    return int(match.group(1))

        # Fallback: check branch pattern like "pull/123"
        branch = vcs.get("branch", "")
        if branch.startswith("pull/"):
            import re

            match = re.match(r"pull/(\d+)", branch)
            if match:
                return int(match.group(1))
        return None

    # Fallback
    return None


@tag(group="metadata")
def gh_pull_req_num(build_run: BuildRunInput) -> Optional[int]:
    """Pull request number (works with GitHub Actions, Travis CI, Circle CI)."""
    return _get_pr_number(build_run)


@tag(group="metadata")
def gh_pr_created_at(
    build_run: BuildRunInput,
    github_client: GitHubClientInput,
) -> Optional[str]:
    """
    Pull request creation timestamp fetched from GitHub API.

    Works with all CI providers since we always fetch from GitHub API.
    """
    pr_number = _get_pr_number(build_run)
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
