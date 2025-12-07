"""
Pipeline API - Endpoints for monitoring pipeline execution history.

Provides:
- List recent pipeline runs
- Get run details
- Get pipeline statistics
- Get DAG information
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Path, Query, HTTPException, status
from pydantic import BaseModel
from pymongo.database import Database

from app.database.mongo import get_db
from app.middleware.auth import get_current_user
from app.repositories.pipeline_run import PipelineRunRepository
from app.pipeline.core.registry import feature_registry


router = APIRouter(prefix="/pipeline", tags=["Pipeline"])


# ============================================================================
# DTOs
# ============================================================================


class NodeResultDTO(BaseModel):
    """Node execution result."""
    node_name: str
    status: str
    duration_ms: float
    features_extracted: List[str]
    error: Optional[str] = None
    warning: Optional[str] = None
    retry_count: int = 0


class PipelineRunDTO(BaseModel):
    """Pipeline run summary."""
    id: str
    build_sample_id: str
    repo_id: str
    workflow_run_id: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[float] = None
    feature_count: int = 0
    nodes_executed: int = 0
    nodes_failed: int = 0
    nodes_skipped: int = 0
    total_retries: int = 0
    dag_version: Optional[str] = None
    errors: List[str] = []
    warnings: List[str] = []
    created_at: datetime


class PipelineRunDetailDTO(PipelineRunDTO):
    """Pipeline run with full details."""
    features_extracted: List[str] = []
    node_results: List[NodeResultDTO] = []


class PipelineStatsDTO(BaseModel):
    """Pipeline statistics."""
    total_runs: int
    completed: int
    failed: int
    success_rate: float
    avg_duration_ms: float
    total_features: int
    total_retries: int
    avg_nodes_executed: float
    period_days: int


class DAGInfoDTO(BaseModel):
    """DAG information."""
    version: str
    node_count: int
    feature_count: int
    nodes: List[str]
    groups: List[str]


class PipelineRunListResponse(BaseModel):
    """Paginated list of pipeline runs."""
    items: List[PipelineRunDTO]
    total: int
    skip: int
    limit: int


# ============================================================================
# Endpoints
# ============================================================================


@router.get("/runs", response_model=PipelineRunListResponse)
async def list_pipeline_runs(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    repo_id: Optional[str] = Query(default=None, description="Filter by repository ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List recent pipeline runs with pagination."""
    repo = PipelineRunRepository(db)

    if repo_id:
        runs, total = repo.find_by_repo(repo_id, skip=skip, limit=limit)
    else:
        runs = repo.find_recent(limit=skip + limit)[skip:skip + limit]
        # For total count when not filtering
        total = repo.collection.count_documents({})

    items = [
        PipelineRunDTO(
            id=str(run.id),
            build_sample_id=str(run.build_sample_id),
            repo_id=str(run.repo_id),
            workflow_run_id=run.workflow_run_id,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_ms=run.duration_ms,
            feature_count=run.feature_count,
            nodes_executed=run.nodes_executed,
            nodes_failed=run.nodes_failed,
            nodes_skipped=run.nodes_skipped,
            total_retries=run.total_retries,
            dag_version=run.dag_version,
            errors=run.errors,
            warnings=run.warnings,
            created_at=run.created_at,
        )
        for run in runs
    ]

    return PipelineRunListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/runs/{run_id}", response_model=PipelineRunDetailDTO)
async def get_pipeline_run(
    run_id: str = Path(..., description="Pipeline run ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get details of a specific pipeline run."""
    repo = PipelineRunRepository(db)
    run = repo.find_by_id(run_id)

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pipeline run not found",
        )

    node_results = [
        NodeResultDTO(
            node_name=nr.node_name,
            status=nr.status,
            duration_ms=nr.duration_ms,
            features_extracted=nr.features_extracted,
            error=nr.error,
            warning=nr.warning,
            retry_count=nr.retry_count,
        )
        for nr in run.node_results
    ]

    return PipelineRunDetailDTO(
        id=str(run.id),
        build_sample_id=str(run.build_sample_id),
        repo_id=str(run.repo_id),
        workflow_run_id=run.workflow_run_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        duration_ms=run.duration_ms,
        feature_count=run.feature_count,
        features_extracted=run.features_extracted,
        nodes_executed=run.nodes_executed,
        nodes_failed=run.nodes_failed,
        nodes_skipped=run.nodes_skipped,
        total_retries=run.total_retries,
        dag_version=run.dag_version,
        errors=run.errors,
        warnings=run.warnings,
        node_results=node_results,
        created_at=run.created_at,
    )


@router.get("/stats", response_model=PipelineStatsDTO)
async def get_pipeline_stats(
    days: int = Query(default=7, ge=1, le=90, description="Number of days to include"),
    repo_id: Optional[str] = Query(default=None, description="Filter by repository ID"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get pipeline execution statistics."""
    repo = PipelineRunRepository(db)

    if repo_id:
        stats = repo.get_stats_by_repo(repo_id)
        stats["period_days"] = 0  # No time filter for repo-specific stats
        stats["total_retries"] = 0
        stats["avg_nodes_executed"] = 0.0
    else:
        stats = repo.get_stats(days=days)

    return PipelineStatsDTO(**stats)


@router.get("/dag", response_model=DAGInfoDTO)
async def get_dag_info(
    current_user: dict = Depends(get_current_user),
):
    """
    Get current DAG configuration.

    Returns information about the feature extraction DAG including
    version hash, nodes, and groups.
    """
    info = feature_registry.get_dag_info()
    return DAGInfoDTO(**info)


@router.get("/dag/visualize")
async def get_dag_visualization(
    current_user: dict = Depends(get_current_user),
):
    """
    Get DAG visualization data for frontend.

    Returns nodes and edges in a format suitable for React Flow.
    """
    from app.pipeline.core.dag import FeatureDAG

    dag = FeatureDAG(feature_registry)
    dag.build()
    levels = dag.get_execution_levels()

    nodes = []
    edges = []
    all_nodes = feature_registry.get_all(enabled_only=True)

    for node_name, meta in all_nodes.items():
        # Find level for this node
        node_level = 0
        for level in levels:
            if node_name in level.node_names:
                node_level = level.level
                break

        nodes.append({
            "id": node_name,
            "type": "extractor",
            "label": node_name.replace("_", " ").title(),
            "features": list(meta.provides),
            "feature_count": len(meta.provides),
            "requires_resources": list(meta.requires_resources),
            "requires_features": list(meta.requires_features),
            "level": node_level,
            "group": meta.group,
        })

        # Create edges for feature dependencies
        for req_feature in meta.requires_features:
            provider = feature_registry.get_provider(req_feature)
            if provider:
                edges.append({
                    "id": f"{provider}->{node_name}",
                    "source": provider,
                    "target": node_name,
                    "type": "feature_dependency",
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "execution_levels": [
            {"level": level.level, "nodes": level.node_names}
            for level in levels
        ],
        "total_features": len(feature_registry.get_all_features()),
        "total_nodes": len(all_nodes),
        "dag_version": feature_registry.get_dag_version(),
    }


@router.delete("/runs/cleanup")
async def cleanup_old_runs(
    days: int = Query(default=30, ge=7, le=365, description="Delete runs older than N days"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete old pipeline runs to free up storage.

    Only available to authenticated users.
    """
    repo = PipelineRunRepository(db)
    deleted_count = repo.cleanup_old_runs(days=days)

    return {
        "message": f"Deleted {deleted_count} pipeline runs older than {days} days",
        "deleted_count": deleted_count,
    }
