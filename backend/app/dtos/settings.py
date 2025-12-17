"""DTOs for application settings."""

from typing import Optional
from pydantic import BaseModel, Field


class CircleCISettingsDto(BaseModel):
    """CircleCI integration settings."""

    enabled: bool = False
    base_url: str = "https://circleci.com/api/v2"
    token: Optional[str] = Field(
        None, description="Token (write-only, returns masked on read)"
    )


class TravisCISettingsDto(BaseModel):
    """Travis CI integration settings."""

    enabled: bool = False
    base_url: str = "https://api.travis-ci.com"
    token: Optional[str] = Field(
        None, description="Token (write-only, returns masked on read)"
    )


class SonarQubeSettingsDto(BaseModel):
    """SonarQube code quality settings."""

    enabled: bool = False
    host_url: str = "http://localhost:9000"
    token: Optional[str] = Field(
        None, description="Token (write-only, returns masked on read)"
    )
    default_project_key: str = "build-risk-ui"
    enabled_metrics: list[str] = Field(
        default_factory=list,
        description="Enabled metric keys (empty = all metrics)",
    )


class TrivySettingsDto(BaseModel):
    """Trivy security scanner settings."""

    enabled: bool = False
    severity: str = "CRITICAL,HIGH,MEDIUM"
    timeout: int = 300
    skip_dirs: str = "node_modules,vendor,.git"
    enabled_metrics: list[str] = Field(
        default_factory=list,
        description="Enabled metric keys (empty = all metrics)",
    )


class NotificationSettingsDto(BaseModel):
    """Notification settings (email only)."""

    email_enabled: bool = False
    email_recipients: str = ""


class ApplicationSettingsResponse(BaseModel):
    """Full application settings response."""

    circleci: CircleCISettingsDto
    travis: TravisCISettingsDto
    sonarqube: SonarQubeSettingsDto
    trivy: TrivySettingsDto
    notifications: NotificationSettingsDto


class ApplicationSettingsUpdateRequest(BaseModel):
    """Update request for application settings."""

    circleci: Optional[CircleCISettingsDto] = None
    travis: Optional[TravisCISettingsDto] = None
    sonarqube: Optional[SonarQubeSettingsDto] = None
    trivy: Optional[TrivySettingsDto] = None
    notifications: Optional[NotificationSettingsDto] = None
