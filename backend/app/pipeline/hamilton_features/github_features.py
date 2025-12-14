"""
GitHub API related features.

Features extracted from GitHub API:
- PR/Issue comments
- Commit comments
- Description complexity
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from hamilton.function_modifiers import extract_fields, tag

from app.pipeline.hamilton_features._inputs import (
    GitHubClientInput,
    RepoInput,
    WorkflowRunInput,
)
from app.pipeline.hamilton_features._retry import with_retry

logger = logging.getLogger(__name__)


@extract_fields(
    {
        "gh_num_issue_comments": int,
        "gh_num_commit_comments": int,
        "gh_num_pr_comments": int,
        "gh_description_complexity": Optional[int],
    }
)
@tag(group="github")
@with_retry(max_attempts=3)
def github_discussion_features(
    github_client: GitHubClientInput,
    repo: RepoInput,
    workflow_run: WorkflowRunInput,
    git_all_built_commits: List[str],
) -> Dict[str, Any]:
    """
    Extract GitHub discussion metrics.

    - Issue comments in 24h window before build
    - Commit comments on all built commits
    - PR review comments if this is a PR build
    - Description complexity (word count of PR title + body)
    """
    client = github_client.client
    full_name = github_client.full_name

    # Get commit list
    commits_to_check = git_all_built_commits
    if not commits_to_check:
        head_sha = workflow_run.head_sha
        commits_to_check = [head_sha] if head_sha else []

    # Extract PR info from payload
    payload = workflow_run.raw_payload
    pull_requests = payload.get("pull_requests", [])
    pr_number = None
    description_complexity = None

    if pull_requests:
        pr_data = pull_requests[0]
        pr_number = pr_data.get("number")
        title = pr_data.get("title", "") or ""
        body = pr_data.get("body", "") or ""
        description_complexity = len(title.split()) + len(body.split())

    # 1. Commit comments
    num_commit_comments = 0
    for sha in commits_to_check:
        try:
            comments = client.list_commit_comments(full_name, sha)
            num_commit_comments += len(comments)
        except Exception as e:
            logger.warning(f"Failed to fetch comments for commit {sha}: {e}")

    # 2. PR comments and complexity
    num_pr_comments = 0
    if pr_number:
        try:
            # Fetch PR details if we don't have complexity yet
            if description_complexity is None:
                pr_details = client.get_pull_request(full_name, pr_number)
                title = pr_details.get("title", "") or ""
                body = pr_details.get("body", "") or ""
                description_complexity = len(title.split()) + len(body.split())

            # Get PR review comments
            pr_comments = client.list_review_comments(full_name, pr_number)
            num_pr_comments = len(pr_comments)
        except Exception as e:
            logger.warning(f"Failed to fetch PR data for #{pr_number}: {e}")

    # 3. Issue comments (within time window around the build)
    num_issue_comments = 0
    if workflow_run.ci_created_at:
        try:
            num_issue_comments = _count_recent_issue_comments(
                client, full_name, workflow_run.ci_created_at
            )
        except Exception as e:
            logger.warning(f"Failed to fetch issue comments: {e}")

    return {
        "gh_num_issue_comments": num_issue_comments,
        "gh_num_commit_comments": num_commit_comments,
        "gh_num_pr_comments": num_pr_comments,
        "gh_description_complexity": description_complexity,
    }


def _count_recent_issue_comments(
    client: Any,
    full_name: str,
    build_time: datetime,
    hours_before: int = 24,
) -> int:
    """Count issue comments in the time window before the build."""
    since = build_time - timedelta(hours=hours_before)

    try:
        comments = client.list_issue_comments(
            full_name,
            since=since.isoformat(),
        )

        # Filter to only those before build time
        count = 0
        for comment in comments:
            created_at = comment.get("created_at", "")
            if created_at:
                comment_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                if comment_time <= build_time:
                    count += 1

        return count
    except Exception:
        return 0
