import logging
from typing import Any, Dict

from datetime import datetime, timezone

from app.models.entities.build_sample import BuildSample
from app.models.entities.imported_repository import ImportedRepository
from app.models.entities.workflow_run import WorkflowRunRaw
from app.repositories.workflow_run import WorkflowRunRepository
from app.services.github.github_client import (
    get_app_github_client,
    get_public_github_client,
)
from pymongo.database import Database

logger = logging.getLogger(__name__)


class GitHubDiscussionExtractor:
    def __init__(self, db: Database):
        self.db = db
        self.workflow_run_repo = WorkflowRunRepository(db)

    def extract(
        self,
        build_sample: BuildSample,
        workflow_run: WorkflowRunRaw,
        repo: ImportedRepository,
    ) -> Dict[str, Any]:
        commit_sha = build_sample.tr_original_commit
        if not commit_sha:
            return self._empty_result()

        # Calculate gh_description_complexity
        payload = workflow_run.raw_payload
        pull_requests = payload.get("pull_requests", [])
        pr_number = None
        description_complexity = None

        if pull_requests:
            pr_data = pull_requests[0]
            pr_number = pr_data.get("number")
            title = pr_data.get("title", "")
            body = pr_data.get("body", "")
            description_complexity = len((title or "").split()) + len(
                (body or "").split()
            )
        elif payload.get("event") == "pull_request":
            # If event is PR but pull_requests list is empty (unlikely but possible in some payloads)
            # Try to get from payload directly
            pr_number = payload.get("number")

        installation_id = repo.installation_id

        try:
            client_context = (
                get_app_github_client(self.db, installation_id)
                if installation_id
                else get_public_github_client()
            )

            with client_context as gh:
                # Fetch PR details if complexity not yet calculated and we have a PR number
                if description_complexity is None and pr_number:
                    try:
                        pr_details = gh.get_pull_request(repo.full_name, pr_number)
                        title = pr_details.get("title", "")
                        body = pr_details.get("body", "")
                        description_complexity = len((title or "").split()) + len(
                            (body or "").split()
                        )
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch PR details for complexity: {e}"
                        )

                # 1. Commit comments (Sum for all built commits)
                num_commit_comments = 0
                commits_to_check = build_sample.git_all_built_commits or [commit_sha]

                # Deduplicate and ensure we have a list
                if isinstance(commits_to_check, str):
                    # Handle if it's stored as string joined by #
                    commits_to_check = commits_to_check.split("#")

                commits_to_check = list(set(commits_to_check))

                for sha in commits_to_check:
                    try:
                        comments = gh.list_commit_comments(repo.full_name, sha)
                        num_commit_comments += len(comments)
                    except Exception as e:
                        logger.warning(
                            f"Failed to fetch comments for commit {sha}: {e}"
                        )

                # 2. PR comments & Issue comments (Filtered by time window)
                num_pr_comments = 0
                num_issue_comments = 0

                if pr_number:
                    # Determine time window
                    end_time = build_sample.gh_build_started_at or datetime.now(
                        timezone.utc
                    )

                    start_time = None
                    if build_sample.tr_prev_build:
                        # Find previous build to get its start time
                        # tr_prev_build is likely the run_number or id.
                        # Let's assume run_number for now as per ingestion logic, but check repo
                        prev_run = self.workflow_run_repo.find_by_repo_and_run_id(
                            str(repo.id), build_sample.tr_prev_build
                        )
                        if prev_run and prev_run.created_at:
                            start_time = prev_run.created_at

                    if not start_time:
                        # Fallback to PR creation time
                        if build_sample.gh_pr_created_at:
                            if isinstance(build_sample.gh_pr_created_at, str):
                                try:
                                    start_time = datetime.fromisoformat(
                                        build_sample.gh_pr_created_at.replace(
                                            "Z", "+00:00"
                                        )
                                    )
                                except ValueError:
                                    pass
                            elif isinstance(build_sample.gh_pr_created_at, datetime):
                                start_time = build_sample.gh_pr_created_at

                    if start_time and end_time:
                        # Ensure timezones match (UTC)
                        if start_time.tzinfo is None:
                            start_time = start_time.replace(tzinfo=timezone.utc)
                        if end_time.tzinfo is None:
                            end_time = end_time.replace(tzinfo=timezone.utc)

                        # PR Review Comments
                        try:
                            reviews = gh.list_review_comments(repo.full_name, pr_number)
                            for comment in reviews:
                                created_at_str = comment.get("created_at")
                                if created_at_str:
                                    created_at = datetime.fromisoformat(
                                        created_at_str.replace("Z", "+00:00")
                                    )
                                    if start_time <= created_at <= end_time:
                                        num_pr_comments += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch review comments for PR {pr_number}: {e}"
                            )

                        # Issue Comments
                        try:
                            issue_comments = gh.list_issue_comments(
                                repo.full_name, pr_number
                            )
                            for comment in issue_comments:
                                created_at_str = comment.get("created_at")
                                if created_at_str:
                                    created_at = datetime.fromisoformat(
                                        created_at_str.replace("Z", "+00:00")
                                    )
                                    if start_time <= created_at <= end_time:
                                        num_issue_comments += 1
                        except Exception as e:
                            logger.warning(
                                f"Failed to fetch issue comments for PR {pr_number}: {e}"
                            )

                return {
                    "gh_num_issue_comments": num_issue_comments,
                    "gh_num_commit_comments": num_commit_comments,
                    "gh_num_pr_comments": num_pr_comments,
                    "gh_description_complexity": description_complexity,
                }

        except Exception as e:
            logger.error(
                f"Failed to extract discussion features for {repo.full_name}: {e}"
            )
            return self._empty_result()

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "gh_num_issue_comments": 0,
            "gh_num_commit_comments": 0,
            "gh_num_pr_comments": 0,
            "gh_description_complexity": None,
        }
