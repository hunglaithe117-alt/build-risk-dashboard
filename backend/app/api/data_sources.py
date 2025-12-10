"""
API endpoints for data sources.

Provides information about available data sources for the frontend
to display in the enrichment wizard.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import settings
from app.middleware.auth import get_current_user
from app.pipeline.sources import (
    DataSourceType,
    DataSourceMetadata,
    data_source_registry,
)

# Import sources to register them
from app.pipeline.sources import git, build_log, github_api, sonarqube, trivy

router = APIRouter(prefix="/data-sources", tags=["Data Sources"])


class DataSourceResponse(BaseModel):
    """Response model for a data source."""

    source_type: str
    display_name: str
    description: str
    icon: str
    requires_config: bool
    config_fields: List[Dict[str, Any]]
    features_count: int
    is_available: bool
    is_configured: bool


class DataSourceListResponse(BaseModel):
    """Response model for listing data sources."""

    sources: List[DataSourceResponse]
    total: int


def _check_source_availability(source_type: DataSourceType) -> tuple[bool, bool]:
    """
    Check if a data source is available and configured.

    Returns (is_available, is_configured) tuple.
    """
    if source_type == DataSourceType.GIT:
        return True, True  # Always available

    if source_type == DataSourceType.BUILD_LOG:
        return True, True  # Always available

    if source_type == DataSourceType.GITHUB_API:
        has_tokens = bool(settings.GITHUB_TOKENS)
        return has_tokens, has_tokens

    if source_type == DataSourceType.SONARQUBE:
        is_configured = bool(settings.SONAR_HOST_URL and settings.SONAR_TOKEN)
        return is_configured, is_configured

    if source_type == DataSourceType.TRIVY:
        # Trivy runs locally, just check if enabled
        return settings.TRIVY_ENABLED, settings.TRIVY_ENABLED

    return False, False


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    _current_user: dict = Depends(get_current_user),
):
    """
    List all available data sources with their configuration status.

    This endpoint is used by the frontend to display data source options
    in the enrichment wizard's Step 3 (Configure Data Sources).
    """
    sources = []

    for source_type, source_class in data_source_registry.get_all().items():
        metadata = source_class.get_metadata()
        is_available, is_configured = _check_source_availability(source_type)

        sources.append(
            DataSourceResponse(
                source_type=source_type.value,
                display_name=metadata.display_name,
                description=metadata.description,
                icon=metadata.icon,
                requires_config=metadata.requires_config,
                config_fields=metadata.config_fields,
                features_count=len(source_class.get_feature_names()),
                is_available=is_available,
                is_configured=is_configured,
            )
        )

    # Sort: available first, then by name
    sources.sort(key=lambda x: (not x.is_available, x.display_name))

    return DataSourceListResponse(
        sources=sources,
        total=len(sources),
    )


@router.get("/{source_type}")
async def get_data_source(
    source_type: str,
    _current_user: dict = Depends(get_current_user),
):
    """
    Get details for a specific data source.
    """
    try:
        st = DataSourceType(source_type)
    except ValueError:
        return {"error": f"Unknown source type: {source_type}"}

    source_class = data_source_registry.get(st)
    if not source_class:
        return {"error": f"Source not found: {source_type}"}

    metadata = source_class.get_metadata()
    is_available, is_configured = _check_source_availability(st)
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


@router.get("/{source_type}/features")
async def get_data_source_features(
    source_type: str,
    _current_user: dict = Depends(get_current_user),
):
    """
    Get all features provided by a specific data source.
    """
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
