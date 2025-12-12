from typing import Any, Dict, List

from pydantic import BaseModel


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


class DataSourceDetailResponse(BaseModel):
    """Response model for data source details."""

    source_type: str
    display_name: str
    description: str
    icon: str
    requires_config: bool
    config_fields: List[Dict[str, Any]]
    features: List[str]
    features_count: int
    is_available: bool
    is_configured: bool
    resource_dependencies: List[str]


class DataSourceFeaturesResponse(BaseModel):
    """Response model for data source features."""

    source_type: str
    features: List[str]
    count: int
