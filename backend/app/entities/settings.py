"""Application settings entity stored in MongoDB."""

from typing import Optional
from pydantic import Field

from .base import BaseEntity


class CircleCISettings(BaseEntity):
    """CircleCI integration settings."""

    enabled: bool = False
    base_url: str = "https://circleci.com/api/v2"
    # Token stored encrypted in DB
    token_encrypted: Optional[str] = None


class TravisCISettings(BaseEntity):
    """Travis CI integration settings."""

    enabled: bool = False
    base_url: str = "https://api.travis-ci.com"
    # Token stored encrypted in DB
    token_encrypted: Optional[str] = None


class SonarQubeSettings(BaseEntity):
    """SonarQube code quality settings."""

    enabled: bool = False
    host_url: str = "http://localhost:9000"
    # Token stored encrypted in DB
    token_encrypted: Optional[str] = None
    default_project_key: str = "build-risk-ui"
    # List of enabled metric keys (empty = all metrics enabled)
    enabled_metrics: list[str] = Field(default_factory=list)


class TrivySettings(BaseEntity):
    """Trivy security scanner settings."""

    enabled: bool = False
    severity: str = "CRITICAL,HIGH,MEDIUM"
    timeout: int = 300  # seconds
    skip_dirs: str = "node_modules,vendor,.git"
    # List of enabled metric keys (empty = all metrics enabled)
    enabled_metrics: list[str] = Field(default_factory=list)


class NotificationSettings(BaseEntity):
    """Notification settings (email only)."""

    email_enabled: bool = False
    email_recipients: str = ""


class ApplicationSettings(BaseEntity):
    """Main application settings document - UI-editable configs only."""

    # Single document ID for settings
    settings_version: int = 1

    # CI Provider settings (URL, username, token/password)
    circleci: CircleCISettings = Field(default_factory=CircleCISettings)
    travis: TravisCISettings = Field(default_factory=TravisCISettings)

    # Integration apps (SonarQube, Trivy)
    sonarqube: SonarQubeSettings = Field(default_factory=SonarQubeSettings)
    trivy: TrivySettings = Field(default_factory=TrivySettings)

    # Notifications (email only)
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
