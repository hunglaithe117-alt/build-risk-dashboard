from datetime import datetime, timezone
from typing import Dict, List, Optional

from pymongo.database import Database

from app.entities.github_installation import GithubInstallation
from .base import BaseRepository


class GithubInstallationRepository(BaseRepository[GithubInstallation]):

    def __init__(self, db: Database):
        super().__init__(db, "github_installations", GithubInstallation)

    def list_all(self) -> List[GithubInstallation]:
        return self.find_many({}, sort=[("installed_at", -1)])

    def find_by_installation_id(
        self, installation_id: str
    ) -> Optional[GithubInstallation]:
        return self.find_one({"installation_id": installation_id})

    def create_installation(
        self,
        installation_id: str,
        account_login: str | None,
        account_type: str | None,
        installed_at: datetime,
    ) -> GithubInstallation:
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
