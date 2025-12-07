"""Feature-related DTOs (Data Transfer Objects)."""

from typing import List, Optional

from pydantic import BaseModel


class FeatureDefinitionResponse(BaseModel):
    """Response model for a single feature definition."""

    id: str
    name: str
    display_name: str
    description: str
    category: str
    source: str
    extractor_node: str
    depends_on_features: List[str]
    depends_on_resources: List[str]
    data_type: str
    nullable: bool = False
    is_active: bool = True
    is_deprecated: bool = False
    example_value: Optional[str] = None
    unit: Optional[str] = None

    class Config:
        from_attributes = True


class FeatureListResponse(BaseModel):
    """Response model for list of features."""

    total: int
    items: List[FeatureDefinitionResponse]


class FeatureSummaryResponse(BaseModel):
    """Summary statistics about features."""

    total_features: int
    active_features: int
    deprecated_features: int
    by_category: dict
    by_source: dict
    by_node: dict


class ValidationResponse(BaseModel):
    """Response for validation endpoint."""

    valid: bool
    errors: List[str]
    warnings: List[str]


# DAG Visualization Response Models
class DAGNodeResponse(BaseModel):
    """A node in the DAG (extractor or resource)."""

    id: str
    type: str  # "extractor" or "resource"
    label: str
    features: List[str]
    feature_count: int
    requires_resources: List[str]
    requires_features: List[str]
    level: int


class DAGEdgeResponse(BaseModel):
    """An edge connecting two nodes."""

    id: str
    source: str
    target: str
    type: str  # "feature_dependency" or "resource_dependency"


class ExecutionLevelResponse(BaseModel):
    """A group of nodes that can execute in parallel."""

    level: int
    nodes: List[str]


class DAGResponse(BaseModel):
    """Complete DAG structure for visualization."""

    nodes: List[DAGNodeResponse]
    edges: List[DAGEdgeResponse]
    execution_levels: List[ExecutionLevelResponse]
    total_features: int
    total_nodes: int
