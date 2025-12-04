"""
GitHub API Feature Extractor.

Extracts features that require GitHub API calls.
Matches implementation in extracts/github_discussion_extractor.py.
"""

import logging
from datetime import datetime, timezone
from typing import Set

from app.services.dataset.context import DatasetExtractionContext
from app.services.dataset.extractors.base import BaseFeatureExtractor
from app.repositories.workflow_run import WorkflowRunRepository

logger = logging.getLogger(__name__)


class GitHubFeatureExtractor(BaseFeatureExtractor):
    """
    Extractor for features that require GitHub API access.
    
    Includes comment counts and other API-based metrics.
    Matches implementation in extracts/github_discussion_extractor.py.
    """
    
    SUPPORTED_FEATURES = {
        "gh_num_issue_comments",
        "gh_num_commit_comments",
        "gh_num_pr_comments",
        "gh_description_complexity",
    }
    
    def extract(self, ctx: DatasetExtractionContext, features: Set[str]) -> None:
        """Extract features from GitHub API."""
        from app.services.github.github_client import (
            get_app_github_client,
            get_public_github_client,
        )
        
        if not self.can_extract(features):
            return
        
        installation_id = ctx.repo.installation_id
        
        try:
            client_context = (
                get_app_github_client(ctx.db, installation_id)
                if installation_id
                else get_public_github_client()
            )
            
            with client_context as gh:
                # Extract PR number and description complexity
                pr_number = ctx.features.get("gh_pull_req_num")
                description_complexity = None
                
                payload = ctx.workflow_run.raw_payload or {}
                pull_requests = payload.get("pull_requests", [])
                
                if pull_requests:
                    pr_data = pull_requests[0]
                    if not pr_number:
                        pr_number = pr_data.get("number")
                    title = pr_data.get("title", "")
                    body = pr_data.get("body", "")
                    description_complexity = len((title or "").split()) + len((body or "").split())
                elif payload.get("event") == "pull_request":
                    if not pr_number:
                        pr_number = payload.get("number")
                
                # Fetch PR details if complexity not yet calculated
                if description_complexity is None and pr_number:
                    try:
                        pr_details = gh.get_pull_request(ctx.repo.full_name, pr_number)
                        title = pr_details.get("title", "")
                        body = pr_details.get("body", "")
                        description_complexity = len((title or "").split()) + len((body or "").split())
                    except Exception as e:
                        logger.warning(f"Failed to fetch PR details: {e}")
                
                if "gh_description_complexity" in features:
                    ctx.add_feature("gh_description_complexity", description_complexity)
                
                # 1. Commit comments (Sum for all built commits)
                if "gh_num_commit_comments" in features:
                    num_commit_comments = 0
                    commits_to_check = ctx.git_all_built_commits or [ctx.commit_sha]
                    
                    for sha in commits_to_check:
                        try:
                            comments = gh.list_commit_comments(ctx.repo.full_name, sha)
                            num_commit_comments += len(comments)
                        except Exception as e:
                            logger.warning(f"Failed to fetch comments for commit {sha}: {e}")
                    
                    ctx.add_feature("gh_num_commit_comments", num_commit_comments)
                
                # 2. PR comments & Issue comments (Filtered by time window)
                if "gh_num_pr_comments" in features or "gh_num_issue_comments" in features:
                    num_pr_comments = 0
                    num_issue_comments = 0
                    
                    if pr_number:
                        # Determine time window
                        end_time = ctx.gh_build_started_at or datetime.now(timezone.utc)
                        start_time = None
                        
                        if ctx.tr_prev_build:
                            # Find previous build to get its start time
                            workflow_run_repo = WorkflowRunRepository(ctx.db)
                            prev_run = workflow_run_repo.find_by_repo_and_run_id(
                                str(ctx.repo.id), ctx.tr_prev_build
                            )
                            if prev_run and prev_run.created_at:
                                start_time = prev_run.created_at
                        
                        if not start_time:
                            # Fallback to PR creation time
                            pr_created_at = ctx.gh_pr_created_at
                            if pr_created_at:
                                if isinstance(pr_created_at, str):
                                    try:
                                        start_time = datetime.fromisoformat(
                                            pr_created_at.replace("Z", "+00:00")
                                        )
                                    except ValueError:
                                        pass
                                elif isinstance(pr_created_at, datetime):
                                    start_time = pr_created_at
                        
                        if start_time and end_time:
                            # Ensure timezones match (UTC)
                            if start_time.tzinfo is None:
                                start_time = start_time.replace(tzinfo=timezone.utc)
                            if end_time.tzinfo is None:
                                end_time = end_time.replace(tzinfo=timezone.utc)
                            
                            # PR Review Comments
                            if "gh_num_pr_comments" in features:
                                try:
                                    reviews = gh.list_review_comments(ctx.repo.full_name, pr_number)
                                    for comment in reviews:
                                        created_at_str = comment.get("created_at")
                                        if created_at_str:
                                            created_at = datetime.fromisoformat(
                                                created_at_str.replace("Z", "+00:00")
                                            )
                                            if start_time <= created_at <= end_time:
                                                num_pr_comments += 1
                                except Exception as e:
                                    logger.warning(f"Failed to fetch review comments: {e}")
                            
                            # Issue Comments
                            if "gh_num_issue_comments" in features:
                                try:
                                    issue_comments = gh.list_issue_comments(ctx.repo.full_name, pr_number)
                                    for comment in issue_comments:
                                        created_at_str = comment.get("created_at")
                                        if created_at_str:
                                            created_at = datetime.fromisoformat(
                                                created_at_str.replace("Z", "+00:00")
                                            )
                                            if start_time <= created_at <= end_time:
                                                num_issue_comments += 1
                                except Exception as e:
                                    logger.warning(f"Failed to fetch issue comments: {e}")
                    
                    if "gh_num_pr_comments" in features:
                        ctx.add_feature("gh_num_pr_comments", num_pr_comments)
                    if "gh_num_issue_comments" in features:
                        ctx.add_feature("gh_num_issue_comments", num_issue_comments)
                    
        except Exception as e:
            ctx.add_warning(f"GitHub API extraction failed: {e}")
