from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Query,
    UploadFile,
    status,
)
from fastapi import (
    Path as PathParam,
)
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import (
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdateRequest,
)
from app.middleware.auth import get_current_user
from app.middleware.require_dataset_manager import require_dataset_manager
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.get("/", response_model=DatasetListResponse, response_model_by_alias=False)
def list_datasets(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    q: str | None = Query(default=None, description="Search by name, file, or tag"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List datasets for the signed-in user."""
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")
    service = DatasetService(db)
    return service.list_datasets(user_id, role=role, skip=skip, limit=limit, q=q)


@router.post(
    "/upload",
    response_model=DatasetResponse,
    status_code=status.HTTP_201_CREATED,
    response_model_by_alias=False,
)
async def upload_dataset(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    description: str | None = Form(default=None),
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_dataset_manager),
):
    """Upload a CSV file and create dataset (Admin and Guest)."""
    user_id = str(current_user["_id"])
    upload_fobj = file.file
    try:
        upload_fobj.seek(0)
    except Exception:
        pass

    service = DatasetService(db)
    return service.create_from_upload(
        user_id=user_id,
        filename=file.filename,
        upload_file=upload_fobj,
        name=name,
        description=description,
    )


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def get_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get dataset details."""
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")
    service = DatasetService(db)
    return service.get_dataset(dataset_id, user_id, role=role)


@router.patch(
    "/{dataset_id}",
    response_model=DatasetResponse,
    response_model_by_alias=False,
)
def update_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    payload: DatasetUpdateRequest = Body(...),
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_dataset_manager),
):
    """Update dataset metadata (Admin and Guest)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    return service.update_dataset(dataset_id, user_id, payload)


@router.delete(
    "/{dataset_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_dataset(
    dataset_id: str = PathParam(..., description="Dataset id (Mongo ObjectId)"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(require_dataset_manager),
):
    """Delete a dataset and all associated data (Admin and Guest)."""
    user_id = str(current_user["_id"])
    service = DatasetService(db)
    service.delete_dataset(dataset_id, user_id)
    return None


@router.get("/{dataset_id}/repos")
def list_dataset_repos(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List repositories configured for this dataset.

    Returns repos from dataset_repo_configs with their raw_repo_id
    for drill-down to RawBuildRun via /repos/{raw_repo_id}/builds.
    """
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")
    service = DatasetService(db)
    return service.list_repos(dataset_id, user_id, role=role)


@router.get("/{dataset_id}/builds")
def list_dataset_builds(
    dataset_id: str = PathParam(..., description="Dataset id"),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    status_filter: str | None = Query(
        default=None, description="Filter by status: found/not_found/error"
    ),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List builds for a dataset with enriched details from RawBuildRun."""
    from bson import ObjectId

    from app.repositories.raw_build_run import RawBuildRunRepository

    raw_build_repo = RawBuildRunRepository(db)
    service = DatasetService(db)
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")

    # Access check and dataset existence
    service.get_dataset(dataset_id, user_id, role=role)

    # Build query
    query = {"dataset_id": ObjectId(dataset_id)}
    if status_filter:
        query["status"] = status_filter

    # Get total and items
    total = db.dataset_builds.count_documents(query)
    cursor = db.dataset_builds.find(query).skip(skip).limit(limit).sort("validated_at", -1)

    items = []
    for doc in cursor:
        build_item = {
            "id": str(doc["_id"]),
            "build_id_from_csv": doc.get("build_id_from_csv"),
            "repo_name_from_csv": doc.get("repo_name_from_csv"),
            "status": doc.get("status"),
            "validation_error": doc.get("validation_error"),
            "validated_at": doc.get("validated_at"),
        }

        # Enrich with RawBuildRun data if available
        workflow_run_id = doc.get("workflow_run_id")
        if workflow_run_id:
            raw_build = raw_build_repo.find_by_id(workflow_run_id)
            if raw_build:
                build_item.update(
                    {
                        "build_number": raw_build.build_number,
                        "branch": raw_build.branch,
                        "commit_sha": raw_build.commit_sha,
                        "commit_message": raw_build.commit_message,
                        "commit_author": raw_build.commit_author,
                        "conclusion": raw_build.conclusion,
                        "started_at": raw_build.started_at,
                        "completed_at": raw_build.completed_at,
                        "duration_seconds": raw_build.duration_seconds,
                        "jobs_count": raw_build.jobs_count,
                        "logs_available": raw_build.logs_available,
                        "web_url": raw_build.web_url,
                    }
                )

        items.append(build_item)

    return {
        "items": items,
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.get("/{dataset_id}/builds/stats")
def get_dataset_builds_stats(
    dataset_id: str = PathParam(..., description="Dataset id"),
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get aggregated build stats for charts."""
    from bson import ObjectId

    service = DatasetService(db)
    user_id = str(current_user["_id"])
    role = current_user.get("role", "user")
    # Access check (raises if not permitted)
    service.get_dataset(dataset_id, user_id, role=role)

    oid = ObjectId(dataset_id)

    # Status breakdown (for pie chart)
    status_pipeline = [
        {"$match": {"dataset_id": oid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts = list(db.dataset_builds.aggregate(status_pipeline))
    status_breakdown = {item["_id"]: item["count"] for item in status_counts}

    # Get validated builds for conclusion breakdown
    validated_builds = list(
        db.dataset_builds.find(
            {"dataset_id": oid, "status": "found", "workflow_run_id": {"$ne": None}},
            {"workflow_run_id": 1},
        )
    )

    workflow_ids = [b["workflow_run_id"] for b in validated_builds if b.get("workflow_run_id")]

    # Conclusion breakdown from RawBuildRun
    conclusion_breakdown = {}
    if workflow_ids:
        conclusion_pipeline = [
            {"$match": {"_id": {"$in": workflow_ids}}},
            {"$group": {"_id": "$conclusion", "count": {"$sum": 1}}},
        ]
        conclusion_counts = list(db.raw_build_runs.aggregate(conclusion_pipeline))
        conclusion_breakdown = {item["_id"]: item["count"] for item in conclusion_counts}

    # Builds per repo (for bar chart)
    repo_pipeline = [
        {"$match": {"dataset_id": oid, "status": "found"}},
        {"$group": {"_id": "$repo_name_from_csv", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": 10},
    ]
    repo_counts = list(db.dataset_builds.aggregate(repo_pipeline))
    builds_per_repo = [{"repo": item["_id"], "count": item["count"]} for item in repo_counts]

    # Duration stats
    avg_duration = None
    if workflow_ids:
        duration_result = list(
            db.raw_build_runs.aggregate(
                [
                    {
                        "$match": {
                            "_id": {"$in": workflow_ids},
                            "duration_seconds": {"$ne": None},
                        }
                    },
                    {"$group": {"_id": None, "avg": {"$avg": "$duration_seconds"}}},
                ]
            )
        )
        if duration_result:
            avg_duration = duration_result[0]["avg"]

    # Logs availability
    logs_stats = {"available": 0, "unavailable": 0, "expired": 0}
    if workflow_ids:
        logs_pipeline = [
            {"$match": {"_id": {"$in": workflow_ids}}},
            {
                "$group": {
                    "_id": None,
                    "available": {"$sum": {"$cond": [{"$eq": ["$logs_available", True]}, 1, 0]}},
                    "expired": {"$sum": {"$cond": [{"$eq": ["$logs_expired", True]}, 1, 0]}},
                    "total": {"$sum": 1},
                }
            },
        ]
        logs_result = list(db.raw_build_runs.aggregate(logs_pipeline))
        if logs_result:
            logs_stats["available"] = logs_result[0].get("available", 0)
            logs_stats["expired"] = logs_result[0].get("expired", 0)
            logs_stats["unavailable"] = (
                logs_result[0]["total"] - logs_stats["available"] - logs_stats["expired"]
            )

    return {
        "status_breakdown": status_breakdown,
        "conclusion_breakdown": conclusion_breakdown,
        "builds_per_repo": builds_per_repo,
        "avg_duration_seconds": avg_duration,
        "logs_stats": logs_stats,
        "total_builds": sum(status_breakdown.values()),
        "found_builds": status_breakdown.get("found", 0),
    }
