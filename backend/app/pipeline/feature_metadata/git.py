"""
Git Feature Metadata.

Centralized metadata definitions for all git features:
- commit_info: git_all_built_commits, git_prev_built_commit, etc.
- diff_features: git_diff_src_churn, gh_diff_files_*, etc.
- file_touch_history: gh_num_commits_on_files_touched
- team_membership: gh_by_core_team_member
"""

from app.pipeline.core.registry import (
    FeatureMetadata,
    FeatureCategory,
    FeatureDataType,
    FeatureSource,
)


COMMIT_INFO = {
    "git_all_built_commits": FeatureMetadata(
        display_name="Commits in Build",
        description="List of all commit SHAs included in this build since the last build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.LIST_STRING,
        source=FeatureSource.GIT_REPO,
        example_value="abc123#def456#ghi789",
    ),
    "git_num_all_built_commits": FeatureMetadata(
        display_name="Commit Count",
        description="Number of commits included in this build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="3",
    ),
    "git_prev_built_commit": FeatureMetadata(
        display_name="Previous Built Commit",
        description="SHA of the last commit that had a successful build",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.STRING,
        source=FeatureSource.GIT_REPO,
        example_value="abc123def456",
    ),
    "git_prev_commit_resolution_status": FeatureMetadata(
        display_name="Previous Commit Status",
        description="How the previous build commit was resolved (build_found, merge_found, no_previous_build, commit_not_found)",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.STRING,
        source=FeatureSource.COMPUTED,
        nullable=False,
        example_value="build_found",
    ),
    "tr_prev_build": FeatureMetadata(
        display_name="Previous Build ID",
        description="Workflow run ID of the previous build on the same branch",
        category=FeatureCategory.WORKFLOW,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.METADATA,
        example_value="1234567",
    ),
}

DIFF_FEATURES = {
    "git_diff_src_churn": FeatureMetadata(
        display_name="Source Code Churn",
        description="Total lines added and deleted in source code files",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="245",
        unit="lines",
    ),
    "git_diff_test_churn": FeatureMetadata(
        display_name="Test Code Churn",
        description="Total lines added and deleted in test files",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="87",
        unit="lines",
    ),
    "gh_diff_files_added": FeatureMetadata(
        display_name="Files Added",
        description="Number of new files added in this build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="3",
    ),
    "gh_diff_files_deleted": FeatureMetadata(
        display_name="Files Deleted",
        description="Number of files deleted in this build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="1",
    ),
    "gh_diff_files_modified": FeatureMetadata(
        display_name="Files Modified",
        description="Number of existing files modified in this build",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="8",
    ),
    "gh_diff_tests_added": FeatureMetadata(
        display_name="Tests Added",
        description="Number of new test cases added",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="5",
    ),
    "gh_diff_tests_deleted": FeatureMetadata(
        display_name="Tests Deleted",
        description="Number of test cases removed",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="2",
    ),
    "gh_diff_src_files": FeatureMetadata(
        display_name="Source Files Changed",
        description="Number of source code files changed (including test files)",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="10",
    ),
    "gh_diff_doc_files": FeatureMetadata(
        display_name="Doc Files Changed",
        description="Number of documentation files changed",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="2",
    ),
    "gh_diff_other_files": FeatureMetadata(
        display_name="Other Files Changed",
        description="Number of non-source, non-doc files changed (configs, assets, etc.)",
        category=FeatureCategory.GIT_DIFF,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="4",
    ),
}


FILE_TOUCH_HISTORY = {
    "gh_num_commits_on_files_touched": FeatureMetadata(
        display_name="File History Commits",
        description="Total number of previous commits that touched the same files modified in this build in 3 months",
        category=FeatureCategory.GIT_HISTORY,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="42",
    ),
}

TEAM_MEMBERSHIP = {
    "gh_by_core_team_member": FeatureMetadata(
        display_name="Core Team Commit",
        description="Whether the commit author is a core team member (top contributors)",
        category=FeatureCategory.TEAM,
        data_type=FeatureDataType.BOOLEAN,
        source=FeatureSource.GIT_REPO,
        nullable=False,
        example_value="true",
    ),
    "gh_team_size": FeatureMetadata(
        display_name="Team Size",
        description="Number of unique contributors to the repository in the last 90 days",
        category=FeatureCategory.TEAM,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GIT_REPO,
        example_value="8",
    ),
}


GIT_METADATA = {
    **COMMIT_INFO,
    **DIFF_FEATURES,
    **FILE_TOUCH_HISTORY,
    **TEAM_MEMBERSHIP,
}
