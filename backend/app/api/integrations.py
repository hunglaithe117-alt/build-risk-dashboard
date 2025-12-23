"""
Integration API Endpoints.

Handles:
- List available tools
- SonarQube webhooks (for version-scoped scans)
- Pending scan status checks
"""

import asyncio
import json
from typing import Optional, Set

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos import ToolsListResponse
from app.integrations.registry import get_available_tools
from app.middleware.auth import get_current_user
from app.services.sonar_webhook_service import SonarWebhookService

router = APIRouter(prefix="/integrations", tags=["Integrations"])


# =============================================================================
# Tools
# =============================================================================


@router.get("/tools", response_model=ToolsListResponse)
def list_tools(
    db: Database = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List available integration tools with their status."""
    tools = []
    for tool in get_available_tools():
        tools.append(
            {
                "name": tool.display_name,
                "type": tool.tool_type.value,
                "description": tool.description,
                "scan_mode": tool.scan_mode.value,
                "is_available": tool.is_available(),
                "config": tool.get_config(),
            }
        )
    return {"tools": tools}


# =============================================================================
# SonarQube Pipeline Webhook (for version-scoped scans)
# =============================================================================


@router.post("/webhooks/sonarqube/pipeline")
async def sonarqube_pipeline_webhook(
    request: Request,
    db: Database = Depends(get_db),
    x_sonar_webhook_hmac_sha256: Optional[str] = Header(default=None),
    x_sonar_secret: Optional[str] = Header(default=None),
):
    """
    Handle SonarQube webhook callback for version-scoped scans.

    This is called by SonarQube when analysis completes.
    Metrics are backfilled to DatasetEnrichmentBuild.features.
    """
    body = await request.body()

    service = SonarWebhookService(db)
    service.validate_signature(body, x_sonar_webhook_hmac_sha256, x_sonar_secret)

    payload = json.loads(body.decode("utf-8") or "{}")

    component_key = payload.get("project", {}).get("key")
    if not component_key:
        raise HTTPException(status_code=400, detail="project key missing")

    task_status = payload.get("status")

    return service.handle_pipeline_webhook(component_key, task_status)


@router.get("/sonar/pending/{component_key}")
async def get_sonar_pending_scan(
    component_key: str,
    db: Database = Depends(get_db),
):
    """Check status of a pending SonarQube scan."""
    service = SonarWebhookService(db)
    return service.get_pending_scan(component_key)


@router.get("/sonar/datasets/{dataset_id}/pending")
async def get_sonar_dataset_pending_scans(
    dataset_id: str,
    db: Database = Depends(get_db),
):
    """Get all pending scans for a dataset's enrichment builds."""
    service = SonarWebhookService(db)
    return service.get_dataset_pending_scans(dataset_id)


# =============================================================================
# WebSocket for real-time updates
# =============================================================================

# WebSocket connections store
active_dataset_connections: dict[str, Set[WebSocket]] = {}


@router.websocket("/ws/dataset/{dataset_id}")
async def dataset_scan_websocket(websocket: WebSocket, dataset_id: str):
    """WebSocket for real-time scan updates for a dataset."""
    await websocket.accept()

    # Add to active connections
    if dataset_id not in active_dataset_connections:
        active_dataset_connections[dataset_id] = set()
    active_dataset_connections[dataset_id].add(websocket)

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
        if dataset_id in active_dataset_connections:
            active_dataset_connections[dataset_id].discard(websocket)


async def broadcast_scan_update(dataset_id: str, message: dict):
    """Broadcast scan update to all connected WebSocket clients for a dataset."""
    if dataset_id in active_dataset_connections:
        for websocket in active_dataset_connections[dataset_id]:
            try:
                await websocket.send_json(message)
            except Exception:
                pass
