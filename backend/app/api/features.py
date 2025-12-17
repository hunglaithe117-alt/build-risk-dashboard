from typing import List, Optional

from fastapi import APIRouter, Query

from app.services.feature_service import FeatureService
from app.dtos.feature import (
    FeatureDefinitionResponse,
    FeatureListResponse,
    FeatureSummaryResponse,
    ValidationResponse,
    DAGNodeResponse,
    DAGEdgeResponse,
    ExecutionLevelResponse,
    DAGResponse,
)


router = APIRouter(prefix="/features", tags=["Feature Definitions"])
service = FeatureService()


@router.get("/dag", response_model=DAGResponse)
def get_feature_dag(
    selected_features: Optional[List[str]] = Query(
        None, description="Filter to specific features"
    ),
):
    result = service.get_feature_dag(selected_features)
    return DAGResponse(
        nodes=[DAGNodeResponse(**n) for n in result["nodes"]],
        edges=[DAGEdgeResponse(**e) for e in result["edges"]],
        execution_levels=[
            ExecutionLevelResponse(**l) for l in result["execution_levels"]
        ],
        total_features=result["total_features"],
        total_nodes=result["total_nodes"],
    )


@router.get("/by-node")
def get_features_by_node():
    return service.get_features_by_node()


@router.get("/", response_model=FeatureListResponse)
def list_features(
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    extractor_node: Optional[str] = Query(None, description="Filter by extractor node"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    features = service.list_features(category, source, extractor_node, is_active)
    return FeatureListResponse(
        total=len(features),
        items=[
            FeatureDefinitionResponse(
                id=f["name"],
                name=f["name"],
                display_name=f["display_name"],
                description=f["description"],
                category=f["category"],
                source=f["source"],
                extractor_node=f["extractor_node"],
                depends_on_features=f["depends_on_features"],
                depends_on_resources=f["depends_on_resources"],
                data_type=f["data_type"],
                nullable=False,
                is_active=f["is_active"],
                is_deprecated=False,
                example_value=None,
                unit=None,
            )
            for f in features
        ],
    )


@router.get("/config")
def get_feature_config():
    """
    Get configuration for feature extraction including supported languages and test frameworks.

    Returns:
        - languages: List of supported programming languages
        - frameworks: List of all supported test framework names
        - frameworks_by_language: Test frameworks grouped by language

    Use this to drive UI selection for source languages and test frameworks.
    """
    from app.tasks.pipeline.feature_dag.log_parsers import LogParserRegistry
    from app.tasks.pipeline.feature_dag.languages.registry import LanguageRegistry

    log_parser_registry = LogParserRegistry()

    return {
        "languages": LanguageRegistry.get_supported_languages(),
        "frameworks": log_parser_registry.get_supported_frameworks(),
        "frameworks_by_language": log_parser_registry.get_frameworks_by_language(),
    }


@router.get("/{feature_name}", response_model=FeatureDefinitionResponse)
def get_feature(feature_name: str):
    metadata = service.get_feature(feature_name)
    return FeatureDefinitionResponse(
        id=metadata["name"],
        name=metadata["name"],
        display_name=metadata["display_name"],
        description=metadata["description"],
        category=metadata["category"],
        source=metadata["source"],
        extractor_node=metadata["extractor_node"],
        depends_on_features=metadata["depends_on_features"],
        depends_on_resources=metadata["depends_on_resources"],
        data_type=metadata["data_type"],
        nullable=False,
        is_active=metadata["is_active"],
        is_deprecated=False,
        example_value=None,
        unit=None,
    )


@router.get("/summary/stats", response_model=FeatureSummaryResponse)
def get_feature_summary():
    result = service.get_feature_summary()
    return FeatureSummaryResponse(**result)


@router.get("/validate/all", response_model=ValidationResponse)
def validate_features():
    result = service.validate_features()
    return ValidationResponse(**result)
