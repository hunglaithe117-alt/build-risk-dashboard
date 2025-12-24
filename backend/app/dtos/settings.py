"""DTOs for application settings."""

from typing import Optional

from pydantic import BaseModel, Field


class CircleCISettingsDto(BaseModel):
    """CircleCI integration settings."""

    base_url: str = "https://circleci.com/api/v2"
    token: Optional[str] = Field(None, description="Token (write-only, returns masked on read)")


class TravisCISettingsDto(BaseModel):
    """Travis CI integration settings."""

    base_url: str = "https://api.travis-ci.com"
    token: Optional[str] = Field(None, description="Token (write-only, returns masked on read)")


class SonarQubeSettingsDto(BaseModel):
    """SonarQube code quality settings."""

    host_url: str = "http://localhost:9000"
    token: Optional[str] = Field(None, description="Token (write-only, returns masked on read)")
    webhook_secret: Optional[str] = Field(
        None, description="Webhook secret (write-only, returns masked on read)"
    )
    # Default config content (sonar-project.properties)
    default_config: Optional[str] = Field(
        None, description="Default sonar-project.properties content"
    )


class TrivySettingsDto(BaseModel):
    """Trivy security scanner settings."""

    server_url: Optional[str] = Field(None, description="Trivy server URL for client/server mode")
    # Default config content (trivy.yaml)
    default_config: Optional[str] = Field(None, description="Default trivy.yaml config content")


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
