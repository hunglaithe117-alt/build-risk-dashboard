"""
SonarQube Webhook Service

Handles SonarQube webhook callbacks for pipeline-initiated scans.
Follows app-flow architecture: API → Service → Repository.
"""

import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException
from pymongo.database import Database

from app.config import settings
from app.repositories.sonar_commit_scan import SonarCommitScanRepository

logger = logging.getLogger(__name__)


class SonarWebhookService:
    """Service for handling SonarQube webhook callbacks."""

    def __init__(self, db: Database):
        self.db = db
        self.scan_repo = SonarCommitScanRepository(db)

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
            computed = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
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

        # Find scan record (pipeline-initiated)
        scan_record = self.scan_repo.find_pending_by_component_key(component_key)

        if scan_record:
            # Pipeline-initiated scan - use export_metrics_from_webhook
            from app.tasks.sonar import export_metrics_from_webhook

            export_metrics_from_webhook.delay(
                component_key=component_key,
                analysis_status=task_status or "SUCCESS",
            )

            logger.info(
                f"Queued metrics export for pipeline scan: {component_key}, "
                f"commit {scan_record.commit_sha[:8]}"
            )
            return {
                "received": True,
                "component_key": component_key,
                "source": "pipeline",
                "commit_sha": scan_record.commit_sha,
            }

        # No scan record found
        logger.warning(f"No scan record found for component {component_key}")
        return {
            "received": True,
            "component_key": component_key,
            "tracked": False,
        }

    def get_scan_record(self, component_key: str) -> Dict[str, Any]:
        """
        Get scan record status by component key.

        Args:
            component_key: SonarQube project key

        Returns:
            Scan record info dict.

        Raises:
            HTTPException: If not found.
        """
        scan_record = self.scan_repo.find_by_component_key(component_key)

        if not scan_record:
            raise HTTPException(status_code=404, detail="Scan record not found")

        return {
            "component_key": component_key,
            "status": (
                scan_record.status.value
                if hasattr(scan_record.status, "value")
                else scan_record.status
            ),
            "commit_sha": scan_record.commit_sha,
            "repo_full_name": scan_record.repo_full_name,
            "started_at": (scan_record.started_at.isoformat() if scan_record.started_at else None),
            "completed_at": (
                scan_record.completed_at.isoformat() if scan_record.completed_at else None
            ),
            "has_metrics": scan_record.metrics is not None,
            "error_message": scan_record.error_message,
        }

    def get_version_scans(self, version_id: str) -> Dict[str, Any]:
        """
        Get all scans for a dataset version.

        Args:
            version_id: DatasetVersion ID.

        Returns:
            Dict with list of scans.
        """
        from bson import ObjectId

        scans = self.scan_repo.find_by_version(ObjectId(version_id))

        items = []
        for scan in scans:
            items.append(
                {
                    "component_key": scan.component_key,
                    "status": scan.status.value if hasattr(scan.status, "value") else scan.status,
                    "commit_sha": scan.commit_sha,
                    "repo_full_name": scan.repo_full_name,
                    "started_at": (scan.started_at.isoformat() if scan.started_at else None),
                    "completed_at": (scan.completed_at.isoformat() if scan.completed_at else None),
                    "has_metrics": scan.metrics is not None,
                    "error_message": scan.error_message,
                }
            )

        return {"items": items}
