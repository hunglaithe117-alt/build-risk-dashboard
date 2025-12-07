"""
Feature Definitions API.

Endpoints for querying features from the code registry.
No database dependency - features are defined in code via @register_feature decorator.
"""

from typing import List, Optional
from collections import defaultdict, deque

from fastapi import APIRouter, Query

from app.pipeline.core.registry import feature_registry
from app.pipeline.constants import DEFAULT_FEATURES
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


# Ensure pipeline modules are imported (triggers @register_feature decorators)
import app.pipeline  # noqa: F401, E402


@router.get("/dag", response_model=DAGResponse)
def get_feature_dag(
    selected_features: Optional[List[str]] = Query(
        None, description="Filter to specific features"
    ),
):
    """
    Get the Feature DAG structure for visualization.

    Builds the DAG from code registry (no DB dependency).
    Returns nodes (extractors + resources), edges, and execution levels.
    """
    # Get all nodes from code registry
    all_nodes = feature_registry.get_all(enabled_only=True)

    # Build feature -> node mapping
    feature_to_node: dict[str, str] = {}
    node_features: dict[str, list] = defaultdict(list)
    node_resources: dict[str, set] = defaultdict(set)
    node_feature_deps: dict[str, set] = defaultdict(set)

    for node_name, meta in all_nodes.items():
        for feature in meta.provides:
            # Skip default features
            if feature in DEFAULT_FEATURES:
                continue
            feature_to_node[feature] = node_name
            node_features[node_name].append(feature)

        for resource in meta.requires_resources:
            node_resources[node_name].add(resource)

        for req_feat in meta.requires_features:
            if req_feat not in DEFAULT_FEATURES:
                node_feature_deps[node_name].add(req_feat)

    # Filter if specific features requested
    if selected_features:
        to_include_features = set()
        to_include_nodes = set()
        queue = deque(selected_features)

        while queue:
            feat_name = queue.popleft()
            if feat_name in to_include_features or feat_name not in feature_to_node:
                continue
            to_include_features.add(feat_name)
            node_name = feature_to_node[feat_name]
            to_include_nodes.add(node_name)

            # Add required features from this node's meta
            meta = all_nodes.get(node_name)
            if meta:
                for req_feat in meta.requires_features:
                    if (
                        req_feat not in to_include_features
                        and req_feat in feature_to_node
                    ):
                        queue.append(req_feat)

        # Filter to only needed nodes
        node_features = {
            k: [f for f in v if f in to_include_features]
            for k, v in node_features.items()
            if k in to_include_nodes
        }

    # Build node dependency graph
    node_deps: dict[str, set] = defaultdict(set)
    for node_name, deps in node_feature_deps.items():
        if node_name not in node_features:
            continue
        for dep_feat in deps:
            dep_node = feature_to_node.get(dep_feat)
            if dep_node and dep_node != node_name and dep_node in node_features:
                node_deps[node_name].add(dep_node)

    # Calculate levels (longest path from any root)
    levels_map: dict[str, int] = {}

    def calc_level(node: str) -> int:
        if node in levels_map:
            return levels_map[node]
        deps = node_deps[node]
        if not deps:
            levels_map[node] = 0
        else:
            levels_map[node] = 1 + max(
                calc_level(d) for d in deps if d in node_features
            )
        return levels_map[node]

    for node in node_features:
        calc_level(node)

    # Group nodes by level
    level_nodes: dict[int, list] = defaultdict(list)
    for node, level in levels_map.items():
        level_nodes[level].append(node)

    execution_levels = [
        ExecutionLevelResponse(level=lvl, nodes=sorted(nodes))
        for lvl, nodes in sorted(level_nodes.items())
    ]

    # Collect all unique resources
    all_resources = set()
    for node_name in node_features:
        all_resources.update(node_resources.get(node_name, set()))

    # Build response nodes
    dag_nodes = []

    # Add resource nodes (level -1)
    for res in sorted(all_resources):
        dag_nodes.append(
            DAGNodeResponse(
                id=res,
                type="resource",
                label=res.replace("_", " ").title(),
                features=[],
                feature_count=0,
                requires_resources=[],
                requires_features=[],
                level=-1,
            )
        )

    # Add extractor nodes
    for node_name, features in node_features.items():
        dag_nodes.append(
            DAGNodeResponse(
                id=node_name,
                type="extractor",
                label=node_name.replace("_", " ").title(),
                features=sorted(features),
                feature_count=len(features),
                requires_resources=sorted(node_resources.get(node_name, set())),
                requires_features=sorted(node_feature_deps.get(node_name, set())),
                level=levels_map.get(node_name, 0),
            )
        )

    # Build edges
    edges = []
    edge_id = 0

    # Resource -> Node edges
    for node_name in node_features:
        for res in node_resources.get(node_name, set()):
            edges.append(
                DAGEdgeResponse(
                    id=f"edge_{edge_id}",
                    source=res,
                    target=node_name,
                    type="resource_dependency",
                )
            )
            edge_id += 1

    # Node -> Node edges (feature dependencies)
    for node_name, deps in node_deps.items():
        for dep_node in deps:
            edges.append(
                DAGEdgeResponse(
                    id=f"edge_{edge_id}",
                    source=dep_node,
                    target=node_name,
                    type="feature_dependency",
                )
            )
            edge_id += 1

    return DAGResponse(
        nodes=dag_nodes,
        edges=edges,
        execution_levels=execution_levels,
        total_features=sum(len(f) for f in node_features.values()),
        total_nodes=len(node_features),
    )


@router.get("/", response_model=FeatureListResponse)
def list_features(
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    extractor_node: Optional[str] = Query(None, description="Filter by extractor node"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
):
    """List all feature definitions with optional filters."""
    # Get features from code registry
    all_features = feature_registry.get_features_with_metadata()

    # Filter out default features
    features = [f for f in all_features if f["name"] not in DEFAULT_FEATURES]

    # Apply filters
    if category:
        features = [f for f in features if f["category"] == category]
    if source:
        features = [f for f in features if f["source"] == source]
    if extractor_node:
        features = [f for f in features if f["extractor_node"] == extractor_node]
    if is_active is not None:
        features = [f for f in features if f["is_active"] == is_active]

    return FeatureListResponse(
        total=len(features),
        items=[
            FeatureDefinitionResponse(
                id=f["name"],  # Use name as ID since no DB
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


@router.get("/languages")
def get_supported_languages():
    """
    Get list of languages supported by the feature extraction pipeline.
    """
    from app.pipeline.log_parsers import LogParserRegistry
    from app.pipeline.languages import LanguageRegistry
    
    log_parser_registry = LogParserRegistry()
    
    # Get unique languages from both registries
    log_parser_langs = set(log_parser_registry.get_languages())
    language_strategy_langs = set(LanguageRegistry.get_supported_languages())
    
    # Union of all supported languages
    all_supported = log_parser_langs | language_strategy_langs
    
    return {
        "languages": sorted(all_supported),
        "log_parser_languages": sorted(log_parser_langs),
        "language_strategy_languages": sorted(language_strategy_langs),
    }


@router.get("/{feature_name}", response_model=FeatureDefinitionResponse)
def get_feature(feature_name: str):
    """Get a specific feature by name."""
    metadata = feature_registry.get_feature_metadata(feature_name)

    if not metadata:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404, detail=f"Feature '{feature_name}' not found"
        )

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
    """Get summary statistics about available features."""
    all_features = feature_registry.get_features_with_metadata()

    # Filter out default features for stats
    features = [f for f in all_features if f["name"] not in DEFAULT_FEATURES]

    by_category: dict = {}
    by_source: dict = {}
    by_node: dict = {}

    for f in features:
        cat = f["category"]
        src = f["source"]
        node = f["extractor_node"]

        by_category[cat] = by_category.get(cat, 0) + 1
        by_source[src] = by_source.get(src, 0) + 1
        by_node[node] = by_node.get(node, 0) + 1

    return FeatureSummaryResponse(
        total_features=len(features),
        active_features=sum(1 for f in features if f["is_active"]),
        deprecated_features=0,  # No deprecation in code-only mode
        by_category=by_category,
        by_source=by_source,
        by_node=by_node,
    )


@router.get("/validate/all", response_model=ValidationResponse)
def validate_features():
    """Validate feature definitions in code registry."""
    errors = feature_registry.validate()

    return ValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=[],
    )

