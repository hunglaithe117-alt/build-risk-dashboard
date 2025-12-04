"""
Basic Feature Extractor.

Extracts features directly available from workflow run data.
"""

import logging
from typing import Set

from app.services.dataset.context import DatasetExtractionContext
from app.services.dataset.extractors.base import BaseFeatureExtractor

logger = logging.getLogger(__name__)


class BasicFeatureExtractor(BaseFeatureExtractor):
    """
    Extractor for basic features from workflow run data.
    
    These features are always available without additional API calls or git operations.
    Note: Some features are also extracted by git.py and log.py - they take precedence
    if both are requested.
    """
    
    # Features that are ONLY available from this extractor
    # Other features like tr_build_id, tr_status, etc. are better handled by log.py or git.py
    SUPPORTED_FEATURES = {
        "tr_build_id",
        "gh_project_name",
        "git_trigger_commit",
        "tr_build_number",
        "tr_status",
        "gh_build_started_at",
        "ci_provider",
        "git_branch",
        "gh_is_pr",
        "gh_pull_req_num",
    }
    
    def extract(self, ctx: DatasetExtractionContext, features: Set[str]) -> None:
        """Extract basic features from workflow run data."""
        # Features directly from context
        basic_features = {
            "tr_build_id": ctx.workflow_run.workflow_run_id,
            "gh_project_name": ctx.repo.full_name,
            "git_trigger_commit": ctx.commit_sha,
            "tr_build_number": ctx.build_number,
            "tr_status": ctx.build_status,
            "gh_build_started_at": ctx.workflow_run.created_at,
            "ci_provider": "github_actions",
        }
        
        for name, value in basic_features.items():
            if name in features:
                ctx.add_feature(name, value)
        
        # Extract from raw_payload if available
        if ctx.workflow_run.raw_payload:
            self._extract_from_payload(ctx, features)
    
    def _extract_from_payload(self, ctx: DatasetExtractionContext, features: Set[str]) -> None:
        """Extract features from workflow run raw payload."""
        payload = ctx.workflow_run.raw_payload
        
        if "git_branch" in features:
            branch = payload.get("head_branch")
            ctx.add_feature("git_branch", branch)
        
        if "gh_is_pr" in features:
            is_pr = payload.get("event") == "pull_request"
            ctx.add_feature("gh_is_pr", is_pr)
        
        if "gh_pull_req_num" in features:
            pr_num = None
            if payload.get("event") == "pull_request":
                prs = payload.get("pull_requests", [])
                if prs:
                    pr_num = prs[0].get("number")
            ctx.add_feature("gh_pull_req_num", pr_num)
