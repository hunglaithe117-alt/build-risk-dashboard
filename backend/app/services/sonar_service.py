"""
SonarQube Service - Read-only service for SonarQube results.

Note: Direct scan triggering is now handled by the pipeline's SonarMeasuresNode.
This service only provides read access to scan results and configuration.
"""

import logging
from datetime import datetime
from typing import Optional

from bson import ObjectId
from pymongo.database import Database

from app.entities.failed_scan import FailedScan, ScanStatus
from app.repositories.scan_result import ScanResultRepository
from app.repositories.failed_scan import FailedScanRepository
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.utils.datetime import utc_now


logger = logging.getLogger(__name__)


class SonarService:
    """
    SonarQube service for configuration and results access.

    Note: Scanning is now triggered via pipeline SonarMeasuresNode when users
    select sonar_* features. This service is for reading results only.
    """

    def __init__(self, db: Database):
        self.db = db
        self.scan_result_repo = ScanResultRepository(db)
        self.failed_scan_repo = FailedScanRepository(db)
        self.repo_repo = ModelRepoConfigRepository(db)

    def update_config(self, repo_id: str, config_content: str) -> bool:
        """Update sonar-project.properties content for a repository."""
        return self.repo_repo.update(repo_id, {"sonar_config": config_content})

    def get_config(self, repo_id: str) -> Optional[str]:
        """Get sonar-project.properties content for a repository."""
        repo = self.repo_repo.get(repo_id)
        return repo.sonar_config if repo else None

    def list_results(self, repo_id: str, skip: int = 0, limit: int = 20) -> dict:
        """List scan results (metrics) for a repository."""
        items = self.scan_result_repo.list_by_repo(repo_id, skip, limit)
        total = self.scan_result_repo.count_by_repo(repo_id)
        return {"items": items, "total": total}

    def get_result_by_component(self, component_key: str) -> Optional[dict]:
        """Get scan result by SonarQube component key."""
        return self.scan_result_repo.find_by_component_key(component_key)

    def list_failed_scans(self, repo_id: str, skip: int = 0, limit: int = 20) -> dict:
        """List pending failed scans for a repository."""
        items = self.failed_scan_repo.list_by_repo(
            repo_id, status=ScanStatus.PENDING, skip=skip, limit=limit
        )
        total = self.failed_scan_repo.count_pending_by_repo(repo_id)
        return {"items": items, "total": total}

    def update_failed_scan_config(
        self, failed_scan_id: str, config_content: str
    ) -> FailedScan:
        """Update config override for a failed scan."""
        updated = self.failed_scan_repo.update(
            failed_scan_id,
            {
                "config_override": config_content,
                "config_source": "text",
                "updated_at": utc_now(),
            },
        )
        return updated
