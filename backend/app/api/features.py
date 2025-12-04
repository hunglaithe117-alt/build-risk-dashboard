"""
Feature Definitions API.

Endpoints for managing and querying feature definitions.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, status
from pymongo.database import Database
from pydantic import BaseModel

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.repositories.feature_definition import FeatureDefinitionRepository
from app.models.entities.feature_definition import (
    FeatureDefinition,
    FeatureCategory,
    FeatureSource,
    FeatureDataType,
)


router = APIRouter(prefix="/features", tags=["Feature Definitions"])


# Response models
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
    nullable: bool
    is_active: bool
    is_deprecated: bool
    is_ml_feature: bool
    example_value: Optional[str]
    unit: Optional[str]
    
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
    ml_features: int
    deprecated_features: int
    by_category: dict
    by_source: dict
    by_node: dict


class ValidationResponse(BaseModel):
    """Response for validation endpoint."""
    valid: bool
    errors: List[str]
    warnings: List[str]


class SyncSummaryResponse(BaseModel):
    """Response for sync status."""
    nodes_checked: int
    features_in_code: int
    features_in_db: int
    missing_in_db: List[str]
    extra_in_db: List[str]


@router.get("/", response_model=FeatureListResponse)
def list_features(
    category: Optional[str] = Query(None, description="Filter by category"),
    source: Optional[str] = Query(None, description="Filter by source"),
    extractor_node: Optional[str] = Query(None, description="Filter by extractor node"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    is_ml_feature: Optional[bool] = Query(None, description="Filter ML features only"),
    db: Database = Depends(get_db),
):
    """List all feature definitions with optional filters."""
    repo = FeatureDefinitionRepository(db)
    
    # Build query
    query = {}
    if category:
        query["category"] = category
    if source:
        query["source"] = source
    if extractor_node:
        query["extractor_node"] = extractor_node
    if is_active is not None:
        query["is_active"] = is_active
    if is_ml_feature is not None:
        query["is_ml_feature"] = is_ml_feature
    
    features = repo.find_many(query, sort=[("category", 1), ("name", 1)])
    
    return FeatureListResponse(
        total=len(features),
        items=[
            FeatureDefinitionResponse(
                id=str(f.id),
                name=f.name,
                display_name=f.display_name,
                description=f.description,
                category=f.category,
                source=f.source,
                extractor_node=f.extractor_node,
                depends_on_features=f.depends_on_features,
                depends_on_resources=f.depends_on_resources,
                data_type=f.data_type,
                nullable=f.nullable,
                is_active=f.is_active,
                is_deprecated=f.is_deprecated,
                is_ml_feature=f.is_ml_feature,
                example_value=f.example_value,
                unit=f.unit,
            )
            for f in features
        ],
    )


@router.get("/summary", response_model=FeatureSummaryResponse)
def get_feature_summary(
    db: Database = Depends(get_db),
):
    """Get summary statistics about feature definitions."""
    repo = FeatureDefinitionRepository(db)
    
    all_features = repo.find_many({})
    active = [f for f in all_features if f.is_active]
    ml = [f for f in all_features if f.is_ml_feature and f.is_active]
    deprecated = [f for f in all_features if f.is_deprecated]
    
    # Group by category
    by_category = {}
    for f in active:
        cat = f.category
        by_category[cat] = by_category.get(cat, 0) + 1
    
    # Group by source
    by_source = {}
    for f in active:
        src = f.source
        by_source[src] = by_source.get(src, 0) + 1
    
    # Group by node
    by_node = {}
    for f in active:
        node = f.extractor_node
        by_node[node] = by_node.get(node, 0) + 1
    
    return FeatureSummaryResponse(
        total_features=len(all_features),
        active_features=len(active),
        ml_features=len(ml),
        deprecated_features=len(deprecated),
        by_category=by_category,
        by_source=by_source,
        by_node=by_node,
    )


@router.get("/categories")
def list_categories():
    """List all available feature categories."""
    return {
        "categories": [
            {"value": c.value, "name": c.name}
            for c in FeatureCategory
        ]
    }


@router.get("/sources")
def list_sources():
    """List all available feature sources."""
    return {
        "sources": [
            {"value": s.value, "name": s.name}
            for s in FeatureSource
        ]
    }


@router.get("/data-types")
def list_data_types():
    """List all available data types."""
    return {
        "data_types": [
            {"value": dt.value, "name": dt.name}
            for dt in FeatureDataType
        ]
    }


@router.get("/validate", response_model=ValidationResponse)
def validate_features(
    db: Database = Depends(get_db),
):
    """Validate that DB definitions match code nodes."""
    from app.pipeline.runner import FeaturePipeline
    
    pipeline = FeaturePipeline(db, use_definitions=True)
    errors = pipeline.validate_pipeline()
    
    return ValidationResponse(
        valid=len(errors) == 0,
        errors=errors,
        warnings=[],
    )


@router.get("/sync-status", response_model=SyncSummaryResponse)
def get_sync_status(
    db: Database = Depends(get_db),
):
    """Check sync status between code and DB."""
    from app.pipeline.core.definition_registry import get_definition_registry
    
    registry = get_definition_registry(db)
    summary = registry.sync_from_nodes()
    
    return SyncSummaryResponse(**summary)


@router.get("/{feature_name}", response_model=FeatureDefinitionResponse)
def get_feature(
    feature_name: str,
    db: Database = Depends(get_db),
):
    """Get a specific feature definition by name."""
    repo = FeatureDefinitionRepository(db)
    feature = repo.find_by_name(feature_name)
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature '{feature_name}' not found"
        )
    
    return FeatureDefinitionResponse(
        id=str(feature.id),
        name=feature.name,
        display_name=feature.display_name,
        description=feature.description,
        category=feature.category,
        source=feature.source,
        extractor_node=feature.extractor_node,
        depends_on_features=feature.depends_on_features,
        depends_on_resources=feature.depends_on_resources,
        data_type=feature.data_type,
        nullable=feature.nullable,
        is_active=feature.is_active,
        is_deprecated=feature.is_deprecated,
        is_ml_feature=feature.is_ml_feature,
        example_value=feature.example_value,
        unit=feature.unit,
    )


@router.get("/{feature_name}/dependencies")
def get_feature_dependencies(
    feature_name: str,
    db: Database = Depends(get_db),
):
    """Get dependency information for a feature."""
    from app.pipeline.core.definition_registry import get_definition_registry
    
    registry = get_definition_registry(db)
    info = registry.get_dependency_info(feature_name)
    
    if "error" in info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=info["error"]
        )
    
    return info


@router.post("/seed")
def seed_features(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Seed or update feature definitions from code."""
    from app.seeds.feature_definitions_seed import seed_features as do_seed
    
    count = do_seed(db)
    
    return {
        "status": "success",
        "message": f"Seeded {count} feature definitions",
    }


@router.patch("/{feature_name}/activate")
def activate_feature(
    feature_name: str,
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Activate a feature."""
    repo = FeatureDefinitionRepository(db)
    feature = repo.find_by_name(feature_name)
    
    if not feature:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature '{feature_name}' not found"
        )
    
    repo.update_one(str(feature.id), {"is_active": True, "is_deprecated": False})
    
    return {"status": "success", "message": f"Feature '{feature_name}' activated"}


@router.patch("/{feature_name}/deactivate")
def deactivate_feature(
    feature_name: str,
    reason: str = Query("", description="Reason for deactivation"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Deactivate a feature."""
    repo = FeatureDefinitionRepository(db)
    success = repo.deactivate(feature_name, reason)
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feature '{feature_name}' not found"
        )
    
    return {"status": "success", "message": f"Feature '{feature_name}' deactivated"}
