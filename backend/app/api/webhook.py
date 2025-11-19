from typing import Dict

from fastapi import APIRouter, Depends, Header, Request, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.services.github.github_webhook import handle_github_event, verify_signature

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


@router.post("/github", status_code=status.HTTP_200_OK)
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
    db: Database = Depends(get_db),
):
    """Handle GitHub webhook events."""
    payload_bytes = await request.body()

    # Verify signature
    verify_signature(x_hub_signature_256, payload_bytes)

    # Parse payload
    payload: Dict[str, object] = await request.json()

    # Handle event
    return handle_github_event(db, x_github_event, payload)
