"""Application settings entity stored in MongoDB."""

from typing import Optional

from pydantic import Field

from .base import BaseEntity

DEFAULT_SONARQUBE_CONFIG = """# SonarQube Default Configuration
# This config is used when no custom config is provided during scan

sonar.sources=.
sonar.sourceEncoding=UTF-8
sonar.scm.disabled=true
sonar.java.binaries=.

# Exclude typical non-source / generated / dependencies
sonar.exclusions=**/.git/**,**/.hg/**,**/.svn/**,**/node_modules/**,**/vendor/**,**/dist/**,**/build/**,**/target/**,**/out/**,**/.next/**,**/.nuxt/**,**/.cache/**,**/__pycache__/**,**/*.min.js,**/*.min.css

# (Optional) Avoid scanning huge binaries/assets
sonar.inclusions=**/*
"""

DEFAULT_TRIVY_CONFIG = """# Trivy "max info" default config
# Goal: collect as much data as possible for storage/analysis.

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

# Include all discovered packages (not only vulnerable ones)
list-all-pkgs: true

# Keep unfixed findings too (more complete, noisier)
ignore-unfixed: false

# Output: prefer JSON for DB ingestion
format: json
output: trivy-result.json

# Filesystem scan options
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

  # Skip large/binary files (keeps secret scan sane)
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


class NotificationSettings(BaseEntity):
    """Notification settings (email only)."""

    email_enabled: bool = False
    email_recipients: str = ""


class ApplicationSettings(BaseEntity):
    """Main application settings document - UI-editable configs only."""

    settings_version: int = 1

    # CI Provider settings
    circleci: CircleCISettings = Field(default_factory=CircleCISettings)
    travis: TravisCISettings = Field(default_factory=TravisCISettings)

    # Scan tool settings
    sonarqube: SonarQubeSettings = Field(default_factory=SonarQubeSettings)
    trivy: TrivySettings = Field(default_factory=TrivySettings)

    # Notifications
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
