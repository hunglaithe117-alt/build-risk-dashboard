"""System settings management endpoints."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.models.schemas import SystemSettings, SystemSettingsUpdate

router = APIRouter(prefix="/settings", tags=["Settings"])

DEFAULT_SETTINGS = {
    "_id": "primary",
    "auto_rescan_enabled": True,
    "updated_at": datetime.utcnow(),
    "updated_by": "system",
}


def _serialize_settings(document: dict) -> SystemSettings:
    payload = document.copy()
    payload["updated_at"] = payload.get("updated_at", datetime.utcnow())
    payload["updated_by"] = payload.get("updated_by", "system")
    return SystemSettings(**payload)


@router.get("/", response_model=SystemSettings)
def get_settings(db: Database = Depends(get_db)):
    document = db.system_settings.find_one({"_id": "primary"})
    if not document:
        db.system_settings.update_one(
            {"_id": "primary"}, {"$setOnInsert": DEFAULT_SETTINGS}, upsert=True
        )
        document = db.system_settings.find_one({"_id": "primary"})
    return _serialize_settings(document)


@router.put("/", response_model=SystemSettings)
def update_settings(payload: SystemSettingsUpdate, db: Database = Depends(get_db)):
    existing = db.system_settings.find_one({"_id": "primary"}) or DEFAULT_SETTINGS
    update_doc = existing.copy()
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "updated_by":
            continue
        update_doc[field] = value
    update_doc["updated_at"] = datetime.utcnow()
    update_doc["updated_by"] = payload.updated_by or "admin"

    db.system_settings.update_one({"_id": "primary"}, {"$set": update_doc}, upsert=True)
    return _serialize_settings(update_doc)
