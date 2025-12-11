import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.github_client import GitHubClientHandle
from app.pipeline.feature_metadata.github import DISCUSSION

logger = logging.getLogger(__name__)


@register_feature(
    name="github_discussion_features",
    requires_resources={ResourceNames.GITHUB_CLIENT},
    requires_features={"git_all_built_commits"},
    provides={
        "gh_num_issue_comments",
        "gh_num_commit_comments",
        "gh_num_pr_comments",
        "gh_description_complexity",
    },
    group="github",
    feature_metadata=DISCUSSION,
)
class GitHubDiscussionNode(FeatureNode):
    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        gh_handle: GitHubClientHandle = context.get_resource(
            ResourceNames.GITHUB_CLIENT
        )
        workflow_run = context.workflow_run
        repo = context.repo
        build_sample = context.build_sample

        client = gh_handle.client
        full_name = repo.full_name

        # Get commit list from git_commit_info node
        commits_to_check = context.get_feature("git_all_built_commits", [])
        if not commits_to_check:
            # Fallback to workflow_run.head_sha
            head_sha = workflow_run.head_sha if workflow_run else None
            commits_to_check = [head_sha] if head_sha else []

        # Extract PR info from workflow run
        payload = workflow_run.raw_payload if workflow_run else {}
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
                context.add_warning(f"Failed to fetch commit comments: {e}")

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
                context.add_warning(f"Failed to fetch PR #{pr_number} data: {e}")

        # 3. Issue comments (within time window around the build)
        num_issue_comments = 0
        if workflow_run and workflow_run.ci_created_at:
            try:
                num_issue_comments = self._count_recent_issue_comments(
                    client, full_name, workflow_run.ci_created_at
                )
            except Exception as e:
                logger.warning(f"Failed to fetch issue comments: {e}")
                context.add_warning(f"Failed to fetch issue comments: {e}")

        return {
            "gh_num_issue_comments": num_issue_comments,
            "gh_num_commit_comments": num_commit_comments,
            "gh_num_pr_comments": num_pr_comments,
            "gh_description_complexity": description_complexity,
        }

    def _count_recent_issue_comments(
        self,
        client,
        full_name: str,
        build_time: datetime,
        hours_before: int = 24,
    ) -> int:
        """Count issue comments in the time window before the build."""
        from datetime import timedelta

        since = build_time - timedelta(hours=hours_before)

        try:
            # GitHub API: list issue comments since a date
            comments = client.list_issue_comments(
                full_name,
                since=since.isoformat(),
            )

            # Filter to only those before build time
            count = 0
            for comment in comments:
                created_at = comment.get("created_at", "")
                if created_at:
                    comment_time = datetime.fromisoformat(
                        created_at.replace("Z", "+00:00")
                    )
                    if comment_time <= build_time:
                        count += 1

            return count
        except Exception:
            return 0
