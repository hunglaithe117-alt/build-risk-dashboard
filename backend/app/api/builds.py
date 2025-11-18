"""Build management endpoints backed by MongoDB."""

from datetime import datetime
from typing import Any, Dict, Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, HTTPException, Query
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import BuildDetailResponse, BuildListResponse, BuildCreate

router = APIRouter()


def _parse_build_identifier(build_id: str) -> int | ObjectId:
    """Allow querying builds by numeric Travis/GitHub run id or Mongo ObjectId."""
    if isinstance(build_id, str):
        stripped = build_id.strip()
        if stripped.isdigit():
            return int(stripped)
        try:
            return ObjectId(stripped)
        except (InvalidId, TypeError):
            pass
    raise HTTPException(status_code=400, detail="Invalid build id format")


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

    builds = [BuildDetailResponse.model_validate(doc) for doc in cursor]

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "builds": builds,
    }


@router.get("/{build_id}", response_model=BuildDetailResponse)
async def get_build(build_id: str, db: Database = Depends(get_db)):
    identifier = _parse_build_identifier(build_id)
    build = db.builds.find_one({"_id": identifier})
    if not build:
        raise HTTPException(status_code=404, detail="Build not found")
    return BuildDetailResponse.model_validate(build)


@router.post("/", response_model=BuildDetailResponse)
async def create_build(payload: BuildCreate, db: Database = Depends(get_db)):
    build_data = payload.model_dump(exclude_unset=True)
    features_data = build_data.pop("features", None)

    now = datetime.utcnow()
    build_document: Dict[str, Any] = {
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

    insert_result = db.builds.insert_one(build_document)
    build_document["_id"] = insert_result.inserted_id
    persisted = db.builds.find_one({"_id": insert_result.inserted_id}) or build_document
    return BuildDetailResponse.model_validate(persisted)


@router.delete("/{build_id}")
async def delete_build(build_id: str, db: Database = Depends(get_db)):
    identifier = _parse_build_identifier(build_id)
    result = db.builds.delete_one({"_id": identifier})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Build not found")
    return {"message": "Build deleted successfully"}
