"""
GitHub API related features.

Features extracted from GitHub API:
- PR/Issue comments
- Commit comments
- Description complexity
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from hamilton.function_modifiers import extract_fields, tag

from app.tasks.pipeline.feature_dag._inputs import (
    BuildRunInput,
    GitHubClientInput,
    RepoInput,
)
from app.tasks.pipeline.feature_dag._metadata import (
    FeatureCategory,
    FeatureDataType,
    FeatureResource,
    feature_metadata,
)
from app.tasks.pipeline.feature_dag._retry import with_retry

logger = logging.getLogger(__name__)


@extract_fields(
    {
        "gh_num_issue_comments": int,
        "gh_num_commit_comments": int,
        "gh_num_pr_comments": int,
        "gh_description_complexity": Optional[int],
    }
)
@feature_metadata(
    display_name="GitHub Discussion Features",
    description="PR comments, issue comments, and description complexity",
    category=FeatureCategory.DISCUSSION,
    data_type=FeatureDataType.JSON,
    required_resources=[
        FeatureResource.GITHUB_API,
        FeatureResource.RAW_BUILD_RUNS,
        FeatureResource.BUILD_RUN,
    ],
)
@tag(group="github")
@with_retry(max_attempts=3)
def github_discussion_features(
    github_client: GitHubClientInput,
    repo: RepoInput,
    build_run: BuildRunInput,
    git_all_built_commits: List[str],
    raw_build_runs: Any,
    gh_pull_req_num: Optional[int],
    gh_pr_created_at: Optional[str],
) -> Dict[str, Any]:
    client = github_client.client
    full_name = github_client.full_name

    # Get commit list
    commits_to_check = git_all_built_commits
    if not commits_to_check:
        head_sha = build_run.commit_sha
        commits_to_check = [head_sha] if head_sha else []

    # Build timestamps
    build_start_time = build_run.created_at

    # Find previous build time for PR comment window
    prev_build_start_time = _get_previous_build_start_time(
        raw_build_runs, repo.id, build_run.ci_run_id, build_start_time
    )

    # 1. Commit comments (same as before - no time filter needed)
    num_commit_comments = 0
    for sha in commits_to_check:
        try:
            comments = client.list_commit_comments(full_name, sha)
            num_commit_comments += len(comments)
        except Exception as e:
            logger.warning(f"Failed to fetch comments for commit {sha}: {e}")

    # 2. PR-specific: Issue comments on the PR + code review comments
    num_issue_comments = 0
    num_pr_comments = 0
    description_complexity = None

    # Use pr_number and pr_created_at from Hamilton DAG
    pr_number = gh_pull_req_num
    pr_created_at: Optional[datetime] = None
    if gh_pr_created_at:
        try:
            pr_created_at = datetime.fromisoformat(gh_pr_created_at.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    if pr_number:
        try:
            # Fetch PR details for description complexity
            pr_details = client.get_pull_request(full_name, pr_number)

            # Description complexity
            title = pr_details.get("title", "") or ""
            body = pr_details.get("body", "") or ""
            description_complexity = len(title.split()) + len(body.split())

            # gh_num_issue_comments: Discussion comments on THIS PR
            num_issue_comments = _count_pr_issue_comments(
                client,
                full_name,
                pr_number,
                from_time=pr_created_at,
                to_time=build_start_time,
            )

            # gh_num_pr_comments: Code review comments on THIS PR
            num_pr_comments = _count_pr_review_comments(
                client,
                full_name,
                pr_number,
                from_time=prev_build_start_time or pr_created_at,
                to_time=build_start_time,
            )
        except Exception as e:
            logger.warning(f"Failed to fetch PR data for #{pr_number}: {e}")

    return {
        "gh_num_issue_comments": num_issue_comments,
        "gh_num_commit_comments": num_commit_comments,
        "gh_num_pr_comments": num_pr_comments,
        "gh_description_complexity": description_complexity,
    }


def _get_previous_build_start_time(
    raw_build_runs: Any,
    repo_id: str,
    current_ci_run_id: str,
    current_build_time: Optional[datetime],
) -> Optional[datetime]:
    """Get the start time of the previous build for this repo."""
    from bson import ObjectId

    if not current_build_time:
        return None

    try:
        prev_build = raw_build_runs.find_one(
            {
                "raw_repo_id": ObjectId(repo_id),
                "created_at": {"$lt": current_build_time},
                "ci_run_id": {"$ne": current_ci_run_id},
            },
            sort=[("created_at", -1)],
        )
        if prev_build:
            return prev_build.get("created_at")
    except Exception as e:
        logger.warning(f"Failed to get previous build: {e}")
    return None


def _count_pr_issue_comments(
    client: Any,
    full_name: str,
    pr_number: int,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> int:
    """
    Count discussion comments on a specific PR within time range.

    TravisTorrent logic (line 903-919):
    - Query issue_comments where issue matches the PR
    - Filter by time: from PR creation to build start
    """
    try:
        # GitHub treats PRs as issues for comments
        comments = client.list_issue_comments(full_name, pr_number)

        count = 0
        for comment in comments:
            created_at_str = comment.get("created_at", "")
            if not created_at_str:
                continue

            comment_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

            # Apply time filter
            if from_time and comment_time < from_time:
                continue
            if to_time and comment_time > to_time:
                continue

            count += 1

        return count
    except Exception as e:
        logger.warning(f"Failed to count PR issue comments: {e}")
        return 0


def _count_pr_review_comments(
    client: Any,
    full_name: str,
    pr_number: int,
    from_time: Optional[datetime],
    to_time: Optional[datetime],
) -> int:
    """
    Count code review comments on a specific PR within time range.

    TravisTorrent logic (line 886-899):
    - Query pull_request_comments
    - Filter by time: from prev_build_started_at to current build_started_at
    """
    try:
        comments = client.list_review_comments(full_name, pr_number)

        count = 0
        for comment in comments:
            created_at_str = comment.get("created_at", "")
            if not created_at_str:
                continue

            comment_time = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

            # Apply time filter
            if from_time and comment_time < from_time:
                continue
            if to_time and comment_time > to_time:
                continue

            count += 1

        return count
    except Exception as e:
        logger.warning(f"Failed to count PR review comments: {e}")
        return 0
