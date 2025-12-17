"""SonarQube configuration access helpers.

Provides merged settings (ENV + DB) for runtime components like runners.
"""

from dataclasses import dataclass
from typing import Optional

from pymongo.database import Database

from app.database.mongo import get_database
from app.services.settings_service import SettingsService


@dataclass(frozen=True)
class SonarRuntimeConfig:
    host_url: str
    token: str
    default_project_key: Optional[str] = None


def get_sonar_runtime_config(db: Database | None = None) -> SonarRuntimeConfig:
    """Return SonarQube runtime configuration merged from SettingsService.

    Falls back to environment defaults if settings are not in DB.
    """
    _db = db or get_database()
    service = SettingsService(_db)
    settings = service.get_settings()

    # settings.sonarqube.token is masked (****1234) when coming from response;
    # for runtime components, rely on DB-stored encrypted token via service update path.
    # Here we accept masked value only for compatibility, but runner requires a real token
    # provided via ENV or updated through the settings API.
    token = settings.sonarqube.token or ""

    return SonarRuntimeConfig(
        host_url=settings.sonarqube.host_url.rstrip("/"),
        token=token,
        default_project_key=settings.sonarqube.default_project_key,
    )
