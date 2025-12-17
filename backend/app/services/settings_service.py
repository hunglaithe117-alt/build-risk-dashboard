"""Service for managing application settings."""

import logging
from typing import Dict, Any, Optional
from cryptography.fernet import Fernet
import base64
import hashlib

from pymongo.database import Database
from fastapi import HTTPException, status

from app.entities.settings import (
    ApplicationSettings,
    CircleCISettings,
    TravisCISettings,
    SonarQubeSettings,
    TrivySettings,
    NotificationSettings,
)
from app.dtos.settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
    CircleCISettingsDto,
    TravisCISettingsDto,
    SonarQubeSettingsDto,
    TrivySettingsDto,
    NotificationSettingsDto,
)
from app.repositories.settings_repository import SettingsRepository
from app.config import settings as app_config

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings."""

    def __init__(self, db: Database):
        self.db = db
        self.repo = SettingsRepository(db)
        # Use SECRET_KEY for encryption
        self._cipher = self._get_cipher()

    def _get_cipher(self) -> Fernet:
        """Get Fernet cipher for encrypting tokens."""
        # Derive a valid Fernet key from SECRET_KEY
        key = hashlib.sha256(app_config.SECRET_KEY.encode()).digest()
        key_base64 = base64.urlsafe_b64encode(key)
        return Fernet(key_base64)

    def _encrypt_token(self, token: str) -> str:
        """Encrypt a token."""
        if not token:
            return ""
        return self._cipher.encrypt(token.encode()).decode()

    def _decrypt_token(self, encrypted: str) -> str:
        """Decrypt a token."""
        if not encrypted:
            return ""
        try:
            return self._cipher.decrypt(encrypted.encode()).decode()
        except Exception as e:
            logger.error(f"Failed to decrypt token: {e}")
            return ""

    def _mask_token(self, token: Optional[str]) -> Optional[str]:
        """Mask token for display (show last 4 chars)."""
        if not token or len(token) < 8:
            return "****"
        return f"****{token[-4:]}"

    def get_settings(self) -> ApplicationSettingsResponse:
        """Get current application settings (merge env + db)."""
        # Get from database
        db_settings = self.repo.get_settings()

        if not db_settings:
            # Return defaults from env config
            return self._get_default_settings()

        # Decrypt and mask tokens for response
        return ApplicationSettingsResponse(
            circleci=CircleCISettingsDto(
                enabled=db_settings.circleci.enabled,
                base_url=db_settings.circleci.base_url,
                token=self._mask_token(
                    self._decrypt_token(db_settings.circleci.token_encrypted or "")
                ),
            ),
            travis=TravisCISettingsDto(
                enabled=db_settings.travis.enabled,
                base_url=db_settings.travis.base_url,
                token=self._mask_token(
                    self._decrypt_token(db_settings.travis.token_encrypted or "")
                ),
            ),
            sonarqube=SonarQubeSettingsDto(
                enabled=db_settings.sonarqube.enabled,
                host_url=db_settings.sonarqube.host_url,
                token=self._mask_token(
                    self._decrypt_token(db_settings.sonarqube.token_encrypted or "")
                ),
                default_project_key=db_settings.sonarqube.default_project_key,
            ),
            trivy=TrivySettingsDto(
                enabled=db_settings.trivy.enabled,
                severity=db_settings.trivy.severity,
                timeout=db_settings.trivy.timeout,
                skip_dirs=db_settings.trivy.skip_dirs,
            ),
            notifications=NotificationSettingsDto(
                email_enabled=db_settings.notifications.email_enabled,
                email_recipients=db_settings.notifications.email_recipients,
            ),
        )

    def _get_default_settings(self) -> ApplicationSettingsResponse:
        """Get default settings from env config."""
        return ApplicationSettingsResponse(
            circleci=CircleCISettingsDto(
                enabled=bool(app_config.CIRCLECI_TOKEN),
                base_url=app_config.CIRCLECI_BASE_URL,
                token=self._mask_token(app_config.CIRCLECI_TOKEN),
            ),
            travis=TravisCISettingsDto(
                enabled=bool(app_config.TRAVIS_TOKEN),
                base_url=app_config.TRAVIS_BASE_URL,
                token=self._mask_token(app_config.TRAVIS_TOKEN),
            ),
            sonarqube=SonarQubeSettingsDto(
                enabled=bool(app_config.SONAR_TOKEN),
                host_url=app_config.SONAR_HOST_URL,
                token=self._mask_token(app_config.SONAR_TOKEN),
                default_project_key=app_config.SONAR_DEFAULT_PROJECT_KEY,
            ),
            trivy=TrivySettingsDto(
                enabled=app_config.TRIVY_ENABLED,
                severity=app_config.TRIVY_SEVERITY,
                timeout=app_config.TRIVY_TIMEOUT,
                skip_dirs=app_config.TRIVY_SKIP_DIRS,
            ),
            notifications=NotificationSettingsDto(
                email_enabled=False,
                email_recipients="",
            ),
        )

    def update_settings(
        self, request: ApplicationSettingsUpdateRequest
    ) -> ApplicationSettingsResponse:
        """Update application settings."""
        # Get existing or create new
        existing = self.repo.get_settings()
        if not existing:
            existing = ApplicationSettings()

        # Update fields if provided
        if request.circleci:
            circleci_data = request.circleci.model_dump()
            if circleci_data.get("token") and not circleci_data["token"].startswith(
                "****"
            ):
                circleci_data["token_encrypted"] = self._encrypt_token(
                    circleci_data.pop("token")
                )
            else:
                circleci_data.pop("token", None)
            existing.circleci = CircleCISettings(**circleci_data)

        if request.travis:
            travis_data = request.travis.model_dump()
            if travis_data.get("token") and not travis_data["token"].startswith("****"):
                travis_data["token_encrypted"] = self._encrypt_token(
                    travis_data.pop("token")
                )
            else:
                travis_data.pop("token", None)
            existing.travis = TravisCISettings(**travis_data)

        if request.sonarqube:
            sonar_data = request.sonarqube.model_dump()
            if sonar_data.get("token") and not sonar_data["token"].startswith("****"):
                sonar_data["token_encrypted"] = self._encrypt_token(
                    sonar_data.pop("token")
                )
            else:
                sonar_data.pop("token", None)
            existing.sonarqube = SonarQubeSettings(**sonar_data)

        if request.trivy:
            existing.trivy = TrivySettings(**request.trivy.model_dump())

        if request.notifications:
            notif_data = request.notifications.model_dump()
            existing.notifications = NotificationSettings(**notif_data)

        # Save to database
        existing.mark_updated()
        self.repo.upsert_settings(existing)

        # Return updated settings
        return self.get_settings()

    def get_decrypted_token(self, service: str) -> Optional[str]:
        """Get decrypted token for a service (for internal use by runners/tasks)."""
        db_settings = self.repo.get_settings()
        if not db_settings:
            return None

        if service == "circleci":
            return self._decrypt_token(db_settings.circleci.token_encrypted or "")
        elif service == "travis":
            return self._decrypt_token(db_settings.travis.token_encrypted or "")
        elif service == "sonarqube":
            return self._decrypt_token(db_settings.sonarqube.token_encrypted or "")
        return None
