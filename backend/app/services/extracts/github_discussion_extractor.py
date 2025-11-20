import logging
from typing import Any, Dict

from app.models.entities.build_sample import BuildSample
from app.models.entities.imported_repository import ImportedRepository
from app.services.github.github_client import get_app_github_client
from pymongo.database import Database

logger = logging.getLogger(__name__)


class GitHubDiscussionExtractor:
    def __init__(self, db: Database):
        self.db = db

    def extract(
        self, build_sample: BuildSample, repo: ImportedRepository
    ) -> Dict[str, Any]:
        commit_sha = build_sample.tr_original_commit
        if not commit_sha:
            return self._empty_result()

        installation_id = repo.installation_id
        if not installation_id:
            logger.warning(f"No installation ID for repo {repo.full_name}")
            return self._empty_result()

        try:
            with get_app_github_client(self.db, installation_id) as gh:
                # 1. Commit comments
                commit_comments = gh.list_commit_comments(repo.full_name, commit_sha)
                num_commit_comments = len(commit_comments)

                # 2. PR comments & Issue comments
                # We need to find the PR associated with this commit
                # This is tricky. GitHub API lists PRs associated with a commit.
                # GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls

                # GET /repos/{owner}/{repo}/commits/{commit_sha}/pulls

                # Since our client doesn't have list_pulls_for_commit, we might need to add it or use raw request
                try:
                    prs = gh._rest_request(
                        "GET", f"/repos/{repo.full_name}/commits/{commit_sha}/pulls"
                    )
                except Exception as e:
                    # Check if it's a 403 Forbidden error
                    error_str = str(e)
                    if "403" in error_str or (
                        hasattr(e, "response") and e.response.status_code == 403
                    ):
                        logger.warning(
                            f"Missing permissions to list PRs for {repo.full_name}. "
                            "Please ensure the GitHub App has 'Pull requests: Read-only' permission."
                        )
                    else:
                        logger.warning(
                            f"Failed to list PRs for commit {commit_sha}: {e}"
                        )
                    prs = []

                num_pr_comments = 0
                num_issue_comments = 0

                processed_prs = set()

                if isinstance(prs, list):
                    for pr in prs:
                        pr_number = pr.get("number")
                        if not pr_number or pr_number in processed_prs:
                            continue

                        processed_prs.add(pr_number)

                        # PR Review Comments
                        reviews = gh.list_review_comments(repo.full_name, pr_number)
                        num_pr_comments += len(reviews)

                        # Issue Comments (General conversation on PR)
                        issue_comments = gh.list_issue_comments(
                            repo.full_name, pr_number
                        )
                        num_issue_comments += len(issue_comments)

                return {
                    "gh_num_issue_comments": num_issue_comments,
                    "gh_num_commit_comments": num_commit_comments,
                    "gh_num_pr_comments": num_pr_comments,
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
        }
