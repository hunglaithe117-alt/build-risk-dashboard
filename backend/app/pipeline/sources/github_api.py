"""
GitHub API Data Source - Provides features from GitHub API.

Features provided:
- PR/Issue discussions and comments
- GitHub-specific metadata
"""

from typing import List, Set

from app.pipeline.sources import (
    DataSource,
    DataSourceConfig,
    DataSourceMetadata,
    DataSourceType,
    register_data_source,
)
from app.pipeline.core.context import ExecutionContext


@register_data_source(DataSourceType.GITHUB_API)
class GitHubAPIDataSource(DataSource):
    """
    GitHub API data source.

    Uses GitHub API to fetch PR/Issue discussions, comments,
    and other GitHub-specific metadata.
    """

    @classmethod
    def get_metadata(cls) -> DataSourceMetadata:
        return DataSourceMetadata(
            source_type=DataSourceType.GITHUB_API,
            display_name="GitHub API",
            description="Fetch PR/Issue discussions, comments, and GitHub metadata",
            icon="github",
            requires_config=False,
            config_fields=[],
            features_provided=cls.get_feature_names(),
            resource_dependencies={"github_client"},
        )

    @classmethod
    def get_feature_names(cls) -> Set[str]:
        """All features provided by GitHub API feature nodes."""
        return {
            # From discussion.py
            "gh_pr_comments_count",
            "gh_review_comments_count",
            "gh_issue_comments_count",
            "gh_total_discussion_count",
            "gh_assignees_count",
            "gh_reviewers_requested",
            "gh_labels",
            "gh_milestone",
            "gh_is_draft",
            # From snapshot.py (repo info from GitHub API)
            "gh_repo_stars",
            "gh_repo_forks",
            "gh_repo_watchers",
            "gh_repo_open_issues",
            "gh_repo_has_wiki",
            "gh_repo_has_pages",
            "gh_repo_language",
            "gh_repo_license",
            "gh_repo_topics",
            "gh_repo_size_kb",
            "gh_repo_default_branch",
            "gh_repo_is_fork",
            "gh_repo_is_archived",
            "gh_repo_age_days",
        }

    @classmethod
    def get_required_resources(cls) -> Set[str]:
        return {"github_client"}

    @classmethod
    def is_available(cls, context: ExecutionContext) -> bool:
        return context.has_resource("github_client")
