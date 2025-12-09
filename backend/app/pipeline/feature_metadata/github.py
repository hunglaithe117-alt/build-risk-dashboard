from app.pipeline.core.registry import (
    FeatureMetadata,
    FeatureCategory,
    FeatureDataType,
    FeatureSource,
)


DISCUSSION = {
    "gh_num_issue_comments": FeatureMetadata(
        display_name="Issue Comments",
        description="Number of comments on related issues in the 24 hours before the build",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GITHUB_API,
        nullable=False,
        example_value="5",
    ),
    "gh_num_commit_comments": FeatureMetadata(
        display_name="Commit Comments",
        description="Number of comments on commits included in this build",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GITHUB_API,
        nullable=False,
        example_value="2",
    ),
    "gh_num_pr_comments": FeatureMetadata(
        display_name="PR Review Comments",
        description="Number of review comments on the pull request",
        category=FeatureCategory.DISCUSSION,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GITHUB_API,
        nullable=False,
        example_value="8",
    ),
    "gh_description_complexity": FeatureMetadata(
        display_name="PR Description Length",
        description="Word count of the PR title and body combined (complexity indicator)",
        category=FeatureCategory.PR_INFO,
        data_type=FeatureDataType.INTEGER,
        source=FeatureSource.GITHUB_API,
        example_value="156",
        unit="words",
    ),
}


GITHUB_METADATA = {
    **DISCUSSION,
}
