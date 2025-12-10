"""
SonarQube Data Source - Provides code quality metrics.

Features provided:
- Code coverage metrics
- Bug/vulnerability counts
- Code smells and technical debt
- Complexity metrics
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


@register_data_source(DataSourceType.SONARQUBE)
class SonarQubeDataSource(DataSource):
    """
    SonarQube data source.

    Fetches code quality metrics from SonarQube/SonarCloud
    at the build commit.
    """

    @classmethod
    def get_metadata(cls) -> DataSourceMetadata:
        return DataSourceMetadata(
            source_type=DataSourceType.SONARQUBE,
            display_name="SonarQube",
            description="Fetch code quality metrics from SonarQube or SonarCloud",
            icon="shield-check",
            requires_config=True,
            config_fields=[
                {
                    "name": "server_url",
                    "type": "string",
                    "label": "SonarQube Server URL",
                    "description": "URL of your SonarQube/SonarCloud instance",
                    "placeholder": "https://sonarcloud.io",
                    "required": True,
                },
                {
                    "name": "token",
                    "type": "password",
                    "label": "Access Token",
                    "description": "SonarQube API token for authentication",
                    "required": True,
                },
                {
                    "name": "project_key_pattern",
                    "type": "string",
                    "label": "Project Key Pattern",
                    "description": "Pattern to match project keys (e.g., {owner}_{repo})",
                    "placeholder": "{owner}_{repo}",
                    "required": False,
                },
            ],
            features_provided=cls.get_feature_names(),
            resource_dependencies={"sonar_client"},
        )

    @classmethod
    def get_feature_names(cls) -> Set[str]:
        """All features provided by SonarQube."""
        # Note: Full list in feature_metadata/sonar.py
        return {
            # Coverage metrics
            "sonar_coverage",
            "sonar_line_coverage",
            "sonar_branch_coverage",
            "sonar_lines_to_cover",
            "sonar_uncovered_lines",
            "sonar_conditions_to_cover",
            "sonar_uncovered_conditions",
            # Reliability (bugs)
            "sonar_bugs",
            "sonar_reliability_rating",
            "sonar_reliability_remediation_effort",
            # Security (vulnerabilities)
            "sonar_vulnerabilities",
            "sonar_security_rating",
            "sonar_security_remediation_effort",
            "sonar_security_hotspots",
            "sonar_security_hotspots_reviewed",
            "sonar_security_review_rating",
            # Maintainability (code smells)
            "sonar_code_smells",
            "sonar_sqale_index",  # Technical debt
            "sonar_sqale_rating",
            "sonar_sqale_debt_ratio",
            # Complexity
            "sonar_complexity",
            "sonar_cognitive_complexity",
            "sonar_function_complexity",
            "sonar_file_complexity",
            # Duplications
            "sonar_duplicated_lines",
            "sonar_duplicated_lines_density",
            "sonar_duplicated_blocks",
            "sonar_duplicated_files",
            # Size
            "sonar_ncloc",  # Lines of code
            "sonar_lines",
            "sonar_statements",
            "sonar_functions",
            "sonar_classes",
            "sonar_files",
            "sonar_comment_lines",
            "sonar_comment_lines_density",
            # Issues
            "sonar_violations",
            "sonar_blocker_violations",
            "sonar_critical_violations",
            "sonar_major_violations",
            "sonar_minor_violations",
            "sonar_info_violations",
            "sonar_open_issues",
            "sonar_confirmed_issues",
            "sonar_reopened_issues",
            "sonar_new_violations",
            "sonar_new_blocker_violations",
            "sonar_new_critical_violations",
        }

    @classmethod
    def get_required_resources(cls) -> Set[str]:
        return {"sonar_client"}

    @classmethod
    def is_available(cls, context: ExecutionContext) -> bool:
        return context.has_resource("sonar_client")

    @classmethod
    def validate_config(cls, config: DataSourceConfig) -> List[str]:
        errors = []

        if not config.credentials.get("server_url"):
            errors.append("SonarQube server URL is required")
        if not config.credentials.get("token"):
            errors.append("SonarQube access token is required")

        # Validate URL format
        server_url = config.credentials.get("server_url", "")
        if server_url and not (
            server_url.startswith("http://") or server_url.startswith("https://")
        ):
            errors.append("Server URL must start with http:// or https://")

        return errors
