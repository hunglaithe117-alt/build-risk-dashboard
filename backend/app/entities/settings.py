"""Application settings entity stored in MongoDB."""

from typing import Optional

from pydantic import Field

from .base import BaseEntity

DEFAULT_SONARQUBE_CONFIG = """
sonar.sources=.
sonar.sourceEncoding=UTF-8
sonar.scm.disabled=true
sonar.java.binaries=.

sonar.exclusions=**/.git/**,**/.hg/**,**/.svn/**,**/node_modules/**,**/vendor/**,**/dist/**,**/build/**,**/target/**,**/out/**,**/.next/**,**/.nuxt/**,**/.cache/**,**/__pycache__/**,**/*.min.js,**/*.min.css

sonar.inclusions=**/*
"""

DEFAULT_TRIVY_CONFIG = """
timeout: 10m

severity:
  - CRITICAL
  - HIGH
  - MEDIUM
  - LOW
  - UNKNOWN

scanners:
  - vuln
  - misconfig
  - secret
  - license

list-all-pkgs: true

ignore-unfixed: false

format: json
output: trivy-result.json

scan:
  skip-dirs:
    - node_modules
    - vendor
    - .git
    - dist
    - build
    - target
    - out
    - .next
    - .nuxt
    - .cache
    - __pycache__

  skip-files:
    - "**/*.min.js"
    - "**/*.min.css"
    - "**/*.map"
    - "**/*.png"
    - "**/*.jpg"
    - "**/*.jpeg"
    - "**/*.gif"
    - "**/*.pdf"
    - "**/*.zip"
    - "**/*.tar"
    - "**/*.tar.gz"
    - "**/*.tgz"
    - "**/*.jar"
    - "**/*.exe"
    - "**/*.dll"
"""


class CircleCISettings(BaseEntity):
    """CircleCI integration settings."""

    base_url: str = "https://circleci.com/api/v2"
    token_encrypted: Optional[str] = None


class TravisCISettings(BaseEntity):
    """Travis CI integration settings."""

    base_url: str = "https://api.travis-ci.com"
    token_encrypted: Optional[str] = None


class SonarQubeSettings(BaseEntity):
    """
    SonarQube settings.

    - Connection: host_url, token
    - Auth: webhook_secret (for callback verification)
    - Default Config: default_config (sonar-project.properties content)
    """

    # Connection settings
    host_url: str = "http://localhost:9000"
    token_encrypted: Optional[str] = None

    # Webhook auth
    webhook_secret_encrypted: Optional[str] = None

    # Default config content (editable in UI)
    # Used when user doesn't provide custom config during scan
    default_config: str = Field(default=DEFAULT_SONARQUBE_CONFIG)


class TrivySettings(BaseEntity):
    """
    Trivy settings.

    - Connection: server_url (for client/server mode, optional)
    - Default Config: default_config (trivy.yaml content)
    """

    # Connection settings (optional - for server mode)
    server_url: Optional[str] = None

    # Default config content (editable in UI)
    # Used when user doesn't provide custom config during scan
    default_config: str = Field(default=DEFAULT_TRIVY_CONFIG)


class EmailNotificationTypeToggles(BaseEntity):
    """Toggle which notification types trigger email.

    When email is enabled, these toggles control which events
    actually send email notifications to recipients.
    """

    pipeline_completed: bool = False  # Not urgent, default OFF
    pipeline_failed: bool = True  # Important, default ON
    dataset_validation_completed: bool = False  # Not urgent, default OFF
    dataset_enrichment_completed: bool = True  # Important milestone, default ON
    rate_limit_warning: bool = False  # Frequent, default OFF
    rate_limit_exhausted: bool = True  # CRITICAL, always recommended ON
    system_alerts: bool = True  # Important, default ON


class NotificationSettings(BaseEntity):
    """Notification settings (email only)."""

    email_enabled: bool = False
    email_recipients: str = ""
    email_type_toggles: EmailNotificationTypeToggles = Field(
        default_factory=EmailNotificationTypeToggles
    )


class ApplicationSettings(BaseEntity):
    """Main application settings document - UI-editable configs only."""

    # Override id to allow string ID for singleton document
    id: str = Field("app_settings_v1", alias="_id")

    settings_version: int = 1

    # CI Provider settings
    circleci: CircleCISettings = Field(default_factory=CircleCISettings)
    travis: TravisCISettings = Field(default_factory=TravisCISettings)

    # Scan tool settings
    sonarqube: SonarQubeSettings = Field(default_factory=SonarQubeSettings)
    trivy: TrivySettings = Field(default_factory=TrivySettings)

    # Notifications
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
