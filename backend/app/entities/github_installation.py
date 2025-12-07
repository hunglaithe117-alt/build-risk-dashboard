"""GitHub installation entity - tracks GitHub App installations"""

from datetime import datetime

from .base import BaseEntity


class GithubInstallation(BaseEntity):
    installation_id: str
    account_login: str | None = None
    account_type: str | None = None  # "User" or "Organization"
    installed_at: datetime
    revoked_at: datetime | None = None
    uninstalled_at: datetime | None = None
    suspended_at: datetime | None = None
