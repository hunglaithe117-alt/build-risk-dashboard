"""Build management endpoints backed by MongoDB."""

from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.database.mongo import get_db
from app.models.schemas import BuildDetailResponse, BuildListResponse, BuildCreate

router = APIRouter()


def _ensure_iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str):
        return value
    return str(value)


def _serialize_feature_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_serialize_feature_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_feature_value(val) for key, val in value.items()}
    return value


def _serialize_build(document: Dict[str, Any]) -> Dict[str, Any]:
    build = document.copy()
    build["id"] = build.pop("_id")

    for key in ["created_at", "updated_at", "started_at", "completed_at"]:
        if key in build:
            build[key] = _ensure_iso(build.get(key))

    if build.get("features"):
        features = build["features"]
        build["features"] = {
            key: _serialize_feature_value(value) for key, value in features.items()
        }

    return build


def _generate_build_id(db: Database) -> int:
    latest = db.builds.find_one(sort=[("_id", -1)])
    if latest:
        return int(latest["_id"]) + 1
    return 1


def _parse_datetime(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


@router.get("/", response_model=BuildListResponse)
async def get_builds(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    repository: Optional[str] = None,
    status: Optional[str] = None,
    db: Database = Depends(get_db),
):
    filters: Dict[str, Any] = {}
    if repository:
        filters["repository"] = repository
    if status:
        filters["status"] = status

    total = db.builds.count_documents(filters)
    cursor = db.builds.find(filters).sort("created_at", -1).skip(skip).limit(limit)

    builds = [_serialize_build(doc) for doc in cursor]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "builds": builds,
    }


@router.get("/{build_id}", response_model=BuildDetailResponse)
async def get_build(build_id: int, db: Database = Depends(get_db)):
    build = db.builds.find_one({"_id": build_id})
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return _serialize_build(build)


@router.post("/", response_model=BuildDetailResponse)
async def create_build(payload: BuildCreate, db: Database = Depends(get_db)):
    build_id = _generate_build_id(db)
    build_data = payload.model_dump(exclude_unset=True)
    features_data = build_data.pop("features", None)

    now = datetime.utcnow()
    build_document: Dict[str, Any] = {
        "_id": build_id,
        "created_at": _parse_datetime(build_data.get("created_at", now)),
        "updated_at": _parse_datetime(build_data.get("updated_at")),
        "repository": build_data.get("repository"),
        "branch": build_data.get("branch"),
        "commit_sha": build_data.get("commit_sha"),
        "build_number": build_data.get("build_number"),
        "workflow_name": build_data.get("workflow_name"),
        "status": build_data.get("status"),
        "conclusion": build_data.get("conclusion"),
        "started_at": _parse_datetime(build_data.get("started_at")),
        "completed_at": _parse_datetime(build_data.get("completed_at")),
        "duration_seconds": build_data.get("duration_seconds"),
        "author_name": build_data.get("author_name"),
        "author_email": build_data.get("author_email"),
        "url": build_data.get("url"),
        "logs_url": build_data.get("logs_url"),
    }

    if features_data:
        build_document["features"] = features_data

    db.builds.insert_one(build_document)
    return _serialize_build(build_document)


@router.delete("/{build_id}")
async def delete_build(build_id: int, db: Database = Depends(get_db)):
    result = db.builds.delete_one({"_id": build_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Build not found")
    return {"message": "Build deleted successfully"}
