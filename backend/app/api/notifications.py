"""Notification and alert endpoints."""
from datetime import datetime

from fastapi import APIRouter, Depends
from pymongo.database import Database

from app.database.mongo import get_db
from app.models.schemas import NotificationListResponse, NotificationPolicy, NotificationPolicyUpdate

router = APIRouter(prefix="/notifications", tags=["Notifications"])

DEFAULT_POLICY = {
    "_id": "primary",
    "channels": ["email", "slack"],
    "muted_repositories": [],
    "last_updated_at": datetime.utcnow(),
    "last_updated_by": "system",
}


def _serialize_policy(document: dict) -> NotificationPolicy:
    payload = document.copy()
    payload["last_updated_at"] = payload.get("last_updated_at", datetime.utcnow())
    payload["last_updated_by"] = payload.get("last_updated_by", "system")
    return NotificationPolicy(**payload)


@router.get("/events", response_model=NotificationListResponse)
def list_notifications(db: Database = Depends(get_db)):
    events = list(db.notification_events.find().sort("created_at", -1).limit(100))
    return {"notifications": events}


@router.get("/policy", response_model=NotificationPolicy)
def get_notification_policy(db: Database = Depends(get_db)):
    policy = db.notification_policies.find_one({"_id": "primary"})
    if not policy:
        db.notification_policies.update_one({"_id": "primary"}, {"$setOnInsert": DEFAULT_POLICY}, upsert=True)
        policy = db.notification_policies.find_one({"_id": "primary"})
    return _serialize_policy(policy)


@router.put("/policy", response_model=NotificationPolicy)
def update_notification_policy(payload: NotificationPolicyUpdate, db: Database = Depends(get_db)):
    existing = db.notification_policies.find_one({"_id": "primary"}) or DEFAULT_POLICY
    update_doc = existing.copy()
    for field, value in payload.model_dump(exclude_unset=True).items():
        if field == "updated_by":
            continue
        update_doc[field] = value
    update_doc["last_updated_at"] = datetime.utcnow()
    update_doc["last_updated_by"] = payload.updated_by
    db.notification_policies.update_one({"_id": "primary"}, {"$set": update_doc}, upsert=True)
    return _serialize_policy(update_doc)
