"""API endpoints for dataset comparison."""

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.comparison import (
    CompareExternalResponse,
    CompareInternalRequest,
    CompareResponse,
)
from app.middleware.rbac import Permission, RequirePermission
from app.services.comparison_service import ComparisonService

router = APIRouter(prefix="/comparison", tags=["Comparison"])


@router.post("/compare", response_model=CompareResponse)
def compare_internal(
    request: CompareInternalRequest,
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Compare two internal dataset versions.

    Compares features, quality metrics, and row overlap between two versions.
    Can compare versions from the same or different datasets.
    """
    service = ComparisonService(db)
    return service.compare_internal(request)


@router.post("/compare-external", response_model=CompareExternalResponse)
def compare_external(
    dataset_id: str = Form(...),
    version_id: str = Form(...),
    file: UploadFile = File(..., description="CSV file to compare against"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    Compare an internal version with an uploaded external CSV.

    Upload a reference dataset (e.g., TravisTorrent original) to compare
    features and coverage with an enriched version.
    """
    service = ComparisonService(db)
    return service.compare_external(version_id, dataset_id, file)


@router.get("/datasets")
def list_comparable_datasets(
    db: Database = Depends(get_db),
    current_user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS)),
):
    """
    List datasets and versions available for comparison.

    Returns a list of datasets with their completed versions.
    """
    datasets = list(db["datasets"].find({}, {"name": 1, "created_at": 1}))

    result = []
    for ds in datasets:
        versions = list(
            db["dataset_versions"].find(
                {"dataset_id": str(ds["_id"]), "status": "completed"},
                {"name": 1, "version_number": 1, "total_rows": 1, "selected_features": 1},
            )
        )
        if versions:
            result.append(
                {
                    "dataset_id": str(ds["_id"]),
                    "dataset_name": ds.get("name", "Unknown"),
                    "versions": [
                        {
                            "version_id": str(v["_id"]),
                            "version_name": v.get("name") or f"v{v.get('version_number', 0)}",
                            "total_rows": v.get("total_rows", 0),
                            "feature_count": len(v.get("selected_features", [])),
                        }
                        for v in versions
                    ],
                }
            )

    return {"datasets": result}
