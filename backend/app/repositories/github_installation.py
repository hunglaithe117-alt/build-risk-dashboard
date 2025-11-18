"""GitHub installation repository for database operations"""

from datetime import datetime, timezone
from typing import Dict, List

from pymongo.database import Database

from .base import BaseRepository


class GithubInstallationRepository(BaseRepository):
    """Repository for GitHub installation entities"""

    def __init__(self, db: Database):
        super().__init__(db, "github_installations")

    def list_all(self) -> List[Dict]:
        """List all GitHub installations"""
        return self.find_many({}, sort=[("installed_at", -1)])

    def find_by_installation_id(self, installation_id: str) -> Dict | None:
        """Find an installation by its installation ID"""
        return self.find_one({"installation_id": installation_id})

    def create_installation(
        self,
        installation_id: str,
        account_login: str | None,
        account_type: str | None,
        installed_at: datetime,
    ) -> Dict:
        """Create a new installation record"""
        now = datetime.now(timezone.utc)
        doc = {
            "installation_id": installation_id,
            "account_login": account_login,
            "account_type": account_type,
            "installed_at": installed_at,
            "created_at": now,
            "revoked_at": None,
            "uninstalled_at": None,
            "suspended_at": None,
        }
        return self.insert_one(doc)
