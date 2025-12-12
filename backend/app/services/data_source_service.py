from typing import Dict, List, Tuple

from app.config import settings
from app.pipeline.sources import DataSourceType, data_source_registry


class DataSourceService:
    """Service for managing data source information."""

    def list_data_sources(self) -> List[Dict]:
        """List all data sources with configuration status."""
        sources = []

        for source_type, source_class in data_source_registry.get_all().items():
            metadata = source_class.get_metadata()
            is_available, is_configured = self._check_availability(source_type)

            sources.append(
                {
                    "source_type": source_type.value,
                    "display_name": metadata.display_name,
                    "description": metadata.description,
                    "icon": metadata.icon,
                    "requires_config": metadata.requires_config,
                    "config_fields": metadata.config_fields,
                    "features_count": len(source_class.get_feature_names()),
                    "is_available": is_available,
                    "is_configured": is_configured,
                }
            )

        # Sort: available first, then by name
        sources.sort(key=lambda x: (not x["is_available"], x["display_name"]))
        return sources

    def get_data_source(self, source_type: str) -> Dict:
        """Get details for a specific data source."""
        try:
            st = DataSourceType(source_type)
        except ValueError:
            return {"error": f"Unknown source type: {source_type}"}

        source_class = data_source_registry.get(st)
        if not source_class:
            return {"error": f"Source not found: {source_type}"}

        metadata = source_class.get_metadata()
        is_available, is_configured = self._check_availability(st)
        features = source_class.get_feature_names()

        return {
            "source_type": st.value,
            "display_name": metadata.display_name,
            "description": metadata.description,
            "icon": metadata.icon,
            "requires_config": metadata.requires_config,
            "config_fields": metadata.config_fields,
            "features": list(features),
            "features_count": len(features),
            "is_available": is_available,
            "is_configured": is_configured,
            "resource_dependencies": list(metadata.resource_dependencies),
        }

    def get_data_source_features(self, source_type: str) -> Dict:
        """Get all features provided by a specific data source."""
        try:
            st = DataSourceType(source_type)
        except ValueError:
            return {"error": f"Unknown source type: {source_type}", "features": []}

        source_class = data_source_registry.get(st)
        if not source_class:
            return {"error": f"Source not found: {source_type}", "features": []}

        features = source_class.get_feature_names()
        return {
            "source_type": st.value,
            "features": sorted(features),
            "count": len(features),
        }

    def _check_availability(self, source_type: DataSourceType) -> Tuple[bool, bool]:
        """Check if a data source is available and configured."""
        if source_type == DataSourceType.GIT:
            return True, True

        if source_type == DataSourceType.BUILD_LOG:
            return True, True

        if source_type == DataSourceType.GITHUB_API:
            has_tokens = bool(settings.GITHUB_TOKENS)
            return has_tokens, has_tokens

        if source_type == DataSourceType.SONARQUBE:
            is_configured = bool(settings.SONAR_HOST_URL and settings.SONAR_TOKEN)
            return is_configured, is_configured

        if source_type == DataSourceType.TRIVY:
            return settings.TRIVY_ENABLED, settings.TRIVY_ENABLED

        return False, False
