"""
SonarQube Measures Feature Node.

This node extracts SonarQube quality metrics for a commit:
1. Checks if measures already exist (cached)
2. If scan pending → return empty (webhook will fill)
3. Otherwise → start async scan via Celery task
4. Returns empty features with warning (pipeline = partial)

Webhook will update build features when scan completes.
"""

import logging
from typing import Any, Dict

from bson import ObjectId

from app.pipeline.features import FeatureNode
from app.pipeline.core.context import ExecutionContext
from app.pipeline.core.registry import register_feature
from app.services.sonar.exporter import MetricsExporter
from app.config import settings
from app.pipeline.feature_metadata.sonar import SONAR_METADATA

logger = logging.getLogger(__name__)

_exporter = MetricsExporter()
SONAR_METRICS = _exporter.metrics

SONAR_FEATURE_NAMES = {f"sonar_{metric}" for metric in SONAR_METRICS}


@register_feature(
    name="sonar_measures",
    group="sonar",
    requires_resources={"sonar_client"},
    provides=SONAR_FEATURE_NAMES,
    feature_metadata=SONAR_METADATA,
)
class SonarMeasuresNode(FeatureNode):
    """
    Extracts SonarQube quality measures as pipeline features.

    Uses async pattern:
    1. Check cached measures → return if available
    2. Check pending scan → return empty if in progress
    3. Start async scan via Celery task
    4. Return empty features (webhook will fill when done)
    """

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        """
        Extract SonarQube measures for the current build.

        Returns:
            Dict of sonar_{metric_name} -> value (or empty if async scan started)
        """
        try:
            # Get repo and commit info
            repo = context.repo
            build = context.build_sample

            repo_url = getattr(repo, "html_url", None)
            commit_sha = getattr(build, "commit_sha", None) or context.get_feature(
                "git_trigger_commit", None
            )

            if not repo_url:
                logger.warning("Repository URL not available for SonarQube scan")
                return self._get_empty_features()

            if not commit_sha:
                logger.warning("Commit SHA not available for SonarQube scan")
                return self._get_empty_features()

            # Build component key
            project_key_prefix = getattr(
                settings, "SONAR_DEFAULT_PROJECT_KEY", "build-risk"
            )
            repo_name = getattr(repo, "name", "unknown")
            project_key = f"{project_key_prefix}_{repo_name}"
            component_key = f"{project_key}_{commit_sha}"

            # Determine build type
            build_type = self._get_build_type(build)
            build_id = str(build.id)

            # Access DB from context
            db = context.db

            # Import here to avoid circular imports
            from app.repositories.sonar_scan_pending import SonarScanPendingRepository

            pending_repo = SonarScanPendingRepository(db)

            # 1. Check if completed scan exists with metrics
            completed = pending_repo.find_completed_by_component_key(component_key)
            if completed and completed.metrics:
                logger.info(f"Using cached SonarQube metrics for {component_key}")
                return self._format_metrics(completed.metrics)

            # 2. Check if scan is in progress
            if pending_repo.is_pending(component_key):
                context.add_warning(
                    f"SonarQube scan in progress for {component_key}, "
                    "features will be updated via webhook"
                )
                return self._get_empty_features()

            # 3. Check if project already exists in SonarQube
            sonar_client = context.get_resource("sonar_client")
            if sonar_client.runner._project_exists(component_key):
                # Project exists, fetch measures directly
                try:
                    measures = sonar_client.get_measures(component_key)
                    if measures:
                        logger.info(
                            f"Fetched existing SonarQube metrics for {component_key}"
                        )
                        return self._format_metrics(measures)
                except Exception as e:
                    logger.warning(f"Failed to fetch existing measures: {e}")
                    context.add_warning(
                        f"Failed to fetch existing SonarQube measures: {e}"
                    )

            # 4. Start async scan
            from app.tasks.sonar import start_sonar_scan

            # Get config override if available
            config_content = getattr(repo, "sonar_config", None)

            start_sonar_scan.delay(
                build_id=build_id,
                build_type=build_type,
                repo_url=repo_url,
                commit_sha=commit_sha,
                component_key=component_key,
                config_content=config_content,
            )

            context.add_warning(
                f"SonarQube scan started for {component_key}, "
                "features will be updated when scan completes via webhook"
            )
            logger.info(f"Started async SonarQube scan for {component_key}")

            return self._get_empty_features()

        except Exception as e:
            logger.error(f"SonarQube feature extraction failed: {e}")
            context.add_warning(f"SonarQube extraction failed: {e}")
            return self._get_empty_features()

    def _get_build_type(self, build: Any) -> str:
        """Determine if this is a model or enrichment build."""
        # Check class name
        class_name = build.__class__.__name__
        if "Enrichment" in class_name:
            return "enrichment"
        return "model"

    def _format_metrics(self, metrics: Dict) -> Dict[str, Any]:
        """Format raw metrics to sonar_* feature names."""
        features = {}
        for metric_key, value in metrics.items():
            feature_name = f"sonar_{metric_key}"
            features[feature_name] = self._parse_value(value)

        # Fill missing metrics with None
        for metric in SONAR_METRICS:
            feature_name = f"sonar_{metric}"
            if feature_name not in features:
                features[feature_name] = None

        return features

    def _parse_value(self, value: Any) -> Any:
        """Parse SonarQube value to appropriate Python type."""
        if value is None:
            return None

        # Try integer
        try:
            return int(value)
        except (ValueError, TypeError):
            pass

        # Try float
        try:
            return float(value)
        except (ValueError, TypeError):
            pass

        return str(value)

    def _get_empty_features(self) -> Dict[str, Any]:
        """Return dict with all sonar features set to None."""
        return {f"sonar_{metric}": None for metric in SONAR_METRICS}

    @classmethod
    def get_empty_features(cls) -> Dict[str, Any]:
        """Return empty/default values for all features this node provides."""
        return {f"sonar_{metric}": None for metric in SONAR_METRICS}
