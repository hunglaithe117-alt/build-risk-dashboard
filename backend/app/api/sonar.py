"""SonarQube webhook endpoints for receiving scan completion notifications."""

import hashlib
import hmac
import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pymongo.database import Database
from fastapi import Depends

from app.config import settings
from app.database.mongo import get_db
from app.repositories.scan_job import ScanJobRepository

router = APIRouter()
logger = logging.getLogger(__name__)


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

    # Find the scan job by component key
    scan_job_repo = ScanJobRepository(db)
    jobs = (
        scan_job_repo.collection.find({"sonar_component_key": component_key})
        .sort("created_at", -1)
        .limit(1)
    )
    scan_job = next(jobs, None)

    if not scan_job:
        logger.warning(f"No scan job found for component {component_key}")
        raise HTTPException(status_code=404, detail="Scan job not tracked")

    from app.tasks.sonar import export_metrics_from_webhook

    export_metrics_from_webhook.delay(
        component_key=component_key,
        job_id=str(scan_job["_id"]),
    )

    logger.info(
        f"Queued metrics export for component {component_key}, job {scan_job['_id']}"
    )
    return {"received": True, "component_key": component_key}
