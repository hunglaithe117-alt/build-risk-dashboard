"""SonarQube webhook endpoints for receiving scan completion notifications."""

import asyncio
import hashlib
import hmac
import json
import logging
from typing import Optional, List

from fastapi import (
    APIRouter,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pymongo.database import Database
from fastapi import Depends
from bson import ObjectId

from app.config import settings
from app.database.mongo import get_db, get_database
from app.repositories.sonar_scan_pending import SonarScanPendingRepository
from app.repositories.dataset_enrichment_build import DatasetEnrichmentBuildRepository

router = APIRouter()
logger = logging.getLogger(__name__)

# WebSocket connections store
active_connections: dict[str, List[WebSocket]] = {}


def _validate_signature(
    body: bytes, signature: Optional[str], token_header: Optional[str]
) -> None:
    """Validate webhook signature from SonarQube."""
    secret = settings.SONAR_WEBHOOK_SECRET

    # Check for token header (simple auth)
    if token_header:
        if token_header != secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")
        return

    # Check for HMAC signature
    if signature:
        computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed, signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        raise HTTPException(status_code=401, detail="Webhook secret missing")


@router.post("/webhook")
async def sonar_webhook(
    request: Request,
    db: Database = Depends(get_db),
    x_sonar_webhook_hmac_sha256: Optional[str] = Header(default=None),
    x_sonar_secret: Optional[str] = Header(default=None),
) -> dict:
    body = await request.body()
    _validate_signature(body, x_sonar_webhook_hmac_sha256, x_sonar_secret)

    payload = json.loads(body.decode("utf-8") or "{}")
    logger.info(f"Received SonarQube webhook: {payload}")

    # Extract component key
    component_key = payload.get("project", {}).get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="project key missing")

    # Check task status
    task_status = payload.get("status")
    if task_status != "SUCCESS":
        logger.warning(f"SonarQube task not successful: {task_status}")

    # Find pending scan (pipeline-initiated)
    pending_repo = SonarScanPendingRepository(db)
    pending = pending_repo.find_pending_by_component_key(component_key)

    if pending:
        # Pipeline-initiated scan - use export_metrics_from_webhook
        from app.tasks.sonar import export_metrics_from_webhook

        export_metrics_from_webhook.delay(component_key=component_key)

        # Notify WebSocket clients
        await broadcast_scan_update(
            str(pending.build_id),
            {
                "type": "scan_complete",
                "component_key": component_key,
                "status": "completed",
            },
        )

        logger.info(
            f"Queued metrics export for pipeline scan: {component_key}, "
            f"build {pending.build_id}"
        )
        return {
            "received": True,
            "component_key": component_key,
            "source": "pipeline",
            "build_id": str(pending.build_id),
        }

    # No pending scan found
    logger.warning(f"No pending scan found for component {component_key}")
    return {
        "received": True,
        "component_key": component_key,
        "tracked": False,
    }


@router.get("/pending/{component_key}")
async def get_pending_scan(
    component_key: str,
    db: Database = Depends(get_db),
) -> dict:
    """Check status of a pending SonarQube scan."""
    pending_repo = SonarScanPendingRepository(db)
    pending = pending_repo.find_by_component_key(component_key)

    if not pending:
        raise HTTPException(status_code=404, detail="Pending scan not found")

    return {
        "component_key": component_key,
        "status": (
            pending.status.value if hasattr(pending.status, "value") else pending.status
        ),
        "build_id": str(pending.build_id),
        "build_type": pending.build_type,
        "started_at": pending.started_at.isoformat() if pending.started_at else None,
        "completed_at": (
            pending.completed_at.isoformat() if pending.completed_at else None
        ),
        "has_metrics": pending.metrics is not None,
        "error_message": pending.error_message,
    }


@router.get("/dataset/{dataset_id}/pending")
async def get_dataset_pending_scans(
    dataset_id: str,
    db: Database = Depends(get_db),
) -> dict:
    """Get all pending scans for a dataset's enrichment builds."""
    pending_repo = SonarScanPendingRepository(db)

    # Get all pending scans for enrichment builds of this dataset
    pending_scans = list(
        pending_repo.collection.find(
            {
                "build_type": "enrichment",
            }
        )
        .sort("started_at", -1)
        .limit(50)
    )

    items = []
    for scan in pending_scans:
        items.append(
            {
                "component_key": scan.get("component_key"),
                "status": scan.get("status"),
                "build_id": str(scan.get("build_id")),
                "started_at": (
                    scan.get("started_at").isoformat()
                    if scan.get("started_at")
                    else None
                ),
                "completed_at": (
                    scan.get("completed_at").isoformat()
                    if scan.get("completed_at")
                    else None
                ),
                "has_metrics": scan.get("metrics") is not None,
                "error_message": scan.get("error_message"),
            }
        )

    return {"items": items}


@router.websocket("/ws/dataset/{dataset_id}")
async def sonar_dataset_websocket(websocket: WebSocket, dataset_id: str):
    """WebSocket for real-time sonar scan updates for a dataset."""
    await websocket.accept()

    # Add to active connections
    if dataset_id not in active_connections:
        active_connections[dataset_id] = []
    active_connections[dataset_id].append(websocket)

    try:
        while True:
            # Keep connection alive with ping/pong
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        # Remove from active connections
        if dataset_id in active_connections:
            active_connections[dataset_id] = [
                ws for ws in active_connections[dataset_id] if ws != websocket
            ]


async def broadcast_scan_update(build_id: str, message: dict):
    """Broadcast scan update to all connected WebSocket clients."""
    # For simplicity, broadcast to all connections
    # In production, you'd filter by dataset_id
    for dataset_id, connections in active_connections.items():
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except Exception:
                pass
