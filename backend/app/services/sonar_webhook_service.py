"""
SonarQube Webhook Service

Handles SonarQube webhook callbacks for pipeline-initiated scans.
Follows app-flow architecture: API → Service → Repository.
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from pymongo.database import Database

from app.config import settings
from app.repositories.sonar_scan_pending import SonarScanPendingRepository

logger = logging.getLogger(__name__)


class SonarWebhookService:
    """Service for handling SonarQube webhook callbacks."""

    def __init__(self, db: Database):
        self.db = db
        self.pending_repo = SonarScanPendingRepository(db)

    def validate_signature(
        self,
        body: bytes,
        signature: Optional[str],
        token_header: Optional[str],
    ) -> None:
        """
        Validate webhook signature from SonarQube.

        Raises:
            HTTPException: If signature is invalid or missing.
        """
        secret = settings.SONAR_WEBHOOK_SECRET

        # Check for token header (simple auth)
        if token_header:
            if token_header != secret:
                raise HTTPException(status_code=401, detail="Invalid webhook secret")
            return

        # Check for HMAC signature
        if signature:
            computed = hmac.new(
                secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
            if not hmac.compare_digest(computed, signature):
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
        else:
            raise HTTPException(status_code=401, detail="Webhook secret missing")

    def handle_pipeline_webhook(
        self,
        component_key: str,
        task_status: Optional[str],
    ) -> Dict[str, Any]:
        """
        Handle webhook callback for pipeline-initiated scans.

        Args:
            component_key: SonarQube project key
            task_status: Status from SonarQube (SUCCESS, FAILED, etc.)

        Returns:
            Response dict with processing result.
        """
        if task_status != "SUCCESS":
            logger.warning(f"SonarQube task not successful: {task_status}")

        # Find pending scan (pipeline-initiated)
        pending = self.pending_repo.find_pending_by_component_key(component_key)

        if pending:
            # Pipeline-initiated scan - use export_metrics_from_webhook
            from app.tasks.sonar import export_metrics_from_webhook

            export_metrics_from_webhook.delay(component_key=component_key)

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

    def get_pending_scan(self, component_key: str) -> Dict[str, Any]:
        """
        Get pending scan status by component key.

        Args:
            component_key: SonarQube project key

        Returns:
            Pending scan info dict.

        Raises:
            HTTPException: If not found.
        """
        pending = self.pending_repo.find_by_component_key(component_key)

        if not pending:
            raise HTTPException(status_code=404, detail="Pending scan not found")

        return {
            "component_key": component_key,
            "status": (
                pending.status.value
                if hasattr(pending.status, "value")
                else pending.status
            ),
            "build_id": str(pending.build_id),
            "build_type": pending.build_type,
            "started_at": (
                pending.started_at.isoformat() if pending.started_at else None
            ),
            "completed_at": (
                pending.completed_at.isoformat() if pending.completed_at else None
            ),
            "has_metrics": pending.metrics is not None,
            "error_message": pending.error_message,
        }

    def get_dataset_pending_scans(self, dataset_id: str) -> Dict[str, Any]:
        """
        Get all pending scans for a dataset's enrichment builds.

        Args:
            dataset_id: Dataset ID (currently unused, gets all enrichment scans).

        Returns:
            Dict with list of pending scans.
        """
        # Get all pending scans for enrichment builds
        pending_scans = list(
            self.pending_repo.collection.find(
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
