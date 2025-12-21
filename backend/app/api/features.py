from typing import List, Optional

from fastapi import APIRouter, Query

from app.dtos.feature import (
    ConfigFieldSpec,
    ConfigRequirementsRequest,
    ConfigRequirementsResponse,
    DAGEdgeResponse,
    DAGNodeResponse,
    DAGResponse,
    ExecutionLevelResponse,
    FeatureDefinitionResponse,
    FeatureListResponse,
    FeatureSummaryResponse,
    ValidationResponse,
)
from app.services.feature_service import FeatureService

router = APIRouter(prefix="/features", tags=["Feature Definitions"])
service = FeatureService()


@router.get("/dag", response_model=DAGResponse)
def get_feature_dag(
    selected_features: Optional[List[str]] = Query(None, description="Filter to specific features"),
):
    result = service.get_feature_dag(selected_features)
    return DAGResponse(
        nodes=[DAGNodeResponse(**n) for n in result["nodes"]],
        edges=[DAGEdgeResponse(**e) for e in result["edges"]],
        execution_levels=[ExecutionLevelResponse(**l) for l in result["execution_levels"]],
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
                depends_on_features=f.get("depends_on", []),
                depends_on_resources=f.get("depends_on_resources", []),
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
    Get configuration for feature extraction including supported languages,
    test frameworks, and CI providers.

    Returns:
        - languages: List of supported programming languages
        - frameworks: List of all supported test framework names
        - frameworks_by_language: Test frameworks grouped by language
        - ci_providers: List of supported CI providers with labels

    Use this to drive UI selection for source languages, test frameworks, and CI providers.
    """
    from app.ci_providers.factory import CIProviderRegistry
    from app.tasks.pipeline.feature_dag.languages.registry import LanguageRegistry
    from app.tasks.pipeline.feature_dag.log_parsers import LogParserRegistry

    log_parser_registry = LogParserRegistry()

    return {
        "languages": LanguageRegistry.get_supported_languages(),
        "frameworks": log_parser_registry.get_supported_frameworks(),
        "frameworks_by_language": log_parser_registry.get_frameworks_by_language(),
        "ci_providers": CIProviderRegistry.get_all_with_labels(),
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
        depends_on_features=metadata.get("depends_on", []),
        depends_on_resources=metadata.get("depends_on_resources", []),
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


@router.post("/config-requirements", response_model=ConfigRequirementsResponse)
def get_config_requirements(request: ConfigRequirementsRequest):
    """
    Get required config inputs for selected features.

    Given a list of selected features, this endpoint analyzes which Hamilton
    feature functions are needed and returns all config fields they require.

    Example request:
        {
            "selected_features": ["git_diff_src_churn", "tr_log_frameworks", ...]
        }

    Example response:
        {
            "fields": [
                {
                    "name": "source_languages",
                    "type": "list",
                    "required": true,
                    "description": "Main programming languages",
                    "default": [],
                    "options": ["python", "javascript", "java", ...]
                }
            ]
        }
    """
    from app.tasks.pipeline.constants import HAMILTON_MODULES
    from app.tasks.pipeline.feature_dag._metadata import collect_config_requirements
    from app.tasks.pipeline.feature_dag.languages.registry import LanguageRegistry
    from app.tasks.pipeline.feature_dag.log_parsers import LogParserRegistry

    # Collect requirements from features
    requirements = collect_config_requirements(request.selected_features, HAMILTON_MODULES)

    # Build response with enhanced options from registries
    fields = []
    log_parser_registry = LogParserRegistry()

    for field_name, spec in requirements.items():
        field_spec = ConfigFieldSpec(
            name=field_name,
            type=spec["type"],
            scope=spec.get("scope", "repo"),  # Include scope
            required=spec["required"],
            description=spec["description"],
            default=spec.get("default"),
            options=None,
        )

        # Add options for known fields
        if field_name == "source_languages":
            field_spec.options = LanguageRegistry.get_supported_languages()
        elif field_name == "test_frameworks":
            # Grouped by language for custom UI rendering
            field_spec.options = log_parser_registry.get_frameworks_by_language()
        elif field_name == "ci_provider":
            from app.ci_providers.factory import CIProviderRegistry

            field_spec.options = [p.value for p in CIProviderRegistry.get_all_types()]

        fields.append(field_spec)

    # Sort fields by name for consistent ordering
    fields.sort(key=lambda f: f.name)

    return ConfigRequirementsResponse(fields=fields)
