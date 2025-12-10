"""
Git Data Source - Provides commit and diff features from Git repositories.

Features provided:
- Commit info (author, date, message)
- Diff statistics (files changed, additions, deletions)
- File touch history
- Team membership analysis
"""

from typing import Set

from app.pipeline.sources import (
    DataSource,
    DataSourceConfig,
    DataSourceMetadata,
    DataSourceType,
    register_data_source,
)
from app.pipeline.core.context import ExecutionContext


@register_data_source(DataSourceType.GIT)
class GitDataSource(DataSource):
    """
    Git repository data source.

    Clones repositories and extracts commit/diff information
    at the build commit SHA.
    """

    @classmethod
    def get_metadata(cls) -> DataSourceMetadata:
        return DataSourceMetadata(
            source_type=DataSourceType.GIT,
            display_name="Git Repository",
            description="Clone repositories to extract commit and diff information",
            icon="git-branch",
            requires_config=False,
            config_fields=[],
            features_provided=cls.get_feature_names(),
            resource_dependencies={"git_repo"},
        )

    @classmethod
    def get_feature_names(cls) -> Set[str]:
        """All features provided by git-based feature nodes."""
        return {
            # From commit_info.py
            "git_all_built_commits",
            "git_prev_built_commit",
            "git_prev_commit_resolution_status",
            "git_commit_message",
            "git_commit_author",
            "git_commit_created_at",
            "git_first_build_for_commit",
            "git_is_merge_commit",
            # From diff_features.py
            "git_diff_files_modified",
            "git_diff_files_added",
            "git_diff_files_removed",
            "git_diff_lines_added",
            "git_diff_lines_deleted",
            "git_diff_churn",
            "git_diff_subsystems",
            "git_diff_extensions",
            "git_src_churn",
            "git_test_churn",
            "git_doc_churn",
            "git_config_churn",
            "git_total_source_loc",
            "git_total_test_loc",
            "git_test_density",
            "git_age_youngest_file_days",
            "git_age_oldest_file_days",
            "git_age_weighted_mean_days",
            # From file_touch_history.py
            "git_file_uniqueness",
            "git_total_file_touches",
            "git_avg_touches_per_file",
            "git_authors_on_touched_files",
            "git_file_touch_entropy",
            "git_hot_file_count",
            "git_cold_file_count",
            # From team_membership.py
            "git_author_is_core",
            "git_commit_by_core",
            "git_core_contributors",
            "git_author_commits_total",
            "git_author_experience_days",
            "git_author_files_touched",
        }

    @classmethod
    def get_required_resources(cls) -> Set[str]:
        return {"git_repo"}

    @classmethod
    def is_available(cls, context: ExecutionContext) -> bool:
        return context.has_resource("git_repo")
