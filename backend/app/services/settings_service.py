"""Service for managing application settings."""

import base64
import hashlib
import logging
from typing import Optional

from cryptography.fernet import Fernet
from pymongo.database import Database

from app.config import settings as app_config
from app.dtos.settings import (
    ApplicationSettingsResponse,
    ApplicationSettingsUpdateRequest,
    CircleCISettingsDto,
    NotificationSettingsDto,
    SonarQubeSettingsDto,
    TravisCISettingsDto,
    TrivySettingsDto,
)
from app.entities.settings import (
    DEFAULT_SONARQUBE_CONFIG,
    DEFAULT_TRIVY_CONFIG,
    ApplicationSettings,
    CircleCISettings,
    NotificationSettings,
    SonarQubeSettings,
    TravisCISettings,
    TrivySettings,
)
from app.repositories.settings_repository import SettingsRepository

logger = logging.getLogger(__name__)


class SettingsService:
    """Service for managing application settings."""

    def __init__(self, db: Database):
        self.db = db
        self.repo = SettingsRepository(db)
        self._cipher = self._get_cipher()

    def _get_cipher(self) -> Fernet:
        """Get Fernet cipher for encrypting tokens."""
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
        """Get current application settings (merge env + db).

        Priority: DB settings > ENV vars (ENV as fallback when DB not initialized)
        """
        db_settings = self.repo.get_settings()

        if not db_settings:
            # DB settings not initialized yet - return defaults from ENV
            return self._get_default_settings()

        # Build response from DB settings
        return ApplicationSettingsResponse(
            circleci=CircleCISettingsDto(
                base_url=db_settings.circleci.base_url,
                token=self._mask_token(
                    self._decrypt_token(db_settings.circleci.token_encrypted or "")
                ),
            ),
            travis=TravisCISettingsDto(
                base_url=db_settings.travis.base_url,
                token=self._mask_token(
                    self._decrypt_token(db_settings.travis.token_encrypted or "")
                ),
            ),
            sonarqube=SonarQubeSettingsDto(
                host_url=db_settings.sonarqube.host_url,
                token=self._mask_token(
                    self._decrypt_token(db_settings.sonarqube.token_encrypted or "")
                ),
                webhook_secret=self._mask_token(
                    self._decrypt_token(db_settings.sonarqube.webhook_secret_encrypted or "")
                ),
                default_config=db_settings.sonarqube.default_config,
            ),
            trivy=TrivySettingsDto(
                server_url=db_settings.trivy.server_url,
                default_config=db_settings.trivy.default_config,
            ),
            notifications=NotificationSettingsDto(
                email_enabled=db_settings.notifications.email_enabled,
                email_recipients=db_settings.notifications.email_recipients,
            ),
        )

    def _get_default_settings(self) -> ApplicationSettingsResponse:
        """Get default settings from ENV config.

        Used when DB settings are not initialized yet.
        """
        return ApplicationSettingsResponse(
            circleci=CircleCISettingsDto(
                base_url=app_config.CIRCLECI_BASE_URL,
                token=self._mask_token(app_config.CIRCLECI_TOKEN),
            ),
            travis=TravisCISettingsDto(
                base_url=app_config.TRAVIS_BASE_URL,
                token=self._mask_token(app_config.TRAVIS_TOKEN),
            ),
            sonarqube=SonarQubeSettingsDto(
                host_url=app_config.SONAR_HOST_URL,
                token=self._mask_token(app_config.SONAR_TOKEN),
                webhook_secret=self._mask_token(getattr(app_config, "SONAR_WEBHOOK_SECRET", None)),
                default_config=DEFAULT_SONARQUBE_CONFIG,
            ),
            trivy=TrivySettingsDto(
                server_url=getattr(app_config, "TRIVY_SERVER_URL", None),
                default_config=DEFAULT_TRIVY_CONFIG,
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
        existing = self.repo.get_settings()
        if not existing:
            existing = ApplicationSettings()

        # Update CircleCI
        if request.circleci:
            circleci_data = request.circleci.model_dump(exclude_none=True)
            if circleci_data.get("token") and not circleci_data["token"].startswith("****"):
                circleci_data["token_encrypted"] = self._encrypt_token(circleci_data.pop("token"))
            else:
                circleci_data.pop("token", None)
            # Merge with existing
            existing.circleci = CircleCISettings(
                base_url=circleci_data.get("base_url", existing.circleci.base_url),
                token_encrypted=circleci_data.get(
                    "token_encrypted", existing.circleci.token_encrypted
                ),
            )

        # Update Travis
        if request.travis:
            travis_data = request.travis.model_dump(exclude_none=True)
            if travis_data.get("token") and not travis_data["token"].startswith("****"):
                travis_data["token_encrypted"] = self._encrypt_token(travis_data.pop("token"))
            else:
                travis_data.pop("token", None)
            existing.travis = TravisCISettings(
                base_url=travis_data.get("base_url", existing.travis.base_url),
                token_encrypted=travis_data.get("token_encrypted", existing.travis.token_encrypted),
            )

        # Update SonarQube
        if request.sonarqube:
            sonar_data = request.sonarqube.model_dump(exclude_none=True)
            if sonar_data.get("token") and not sonar_data["token"].startswith("****"):
                sonar_data["token_encrypted"] = self._encrypt_token(sonar_data.pop("token"))
            else:
                sonar_data.pop("token", None)
            if sonar_data.get("webhook_secret") and not sonar_data["webhook_secret"].startswith(
                "****"
            ):
                sonar_data["webhook_secret_encrypted"] = self._encrypt_token(
                    sonar_data.pop("webhook_secret")
                )
            else:
                sonar_data.pop("webhook_secret", None)

            existing.sonarqube = SonarQubeSettings(
                host_url=sonar_data.get("host_url", existing.sonarqube.host_url),
                token_encrypted=sonar_data.get(
                    "token_encrypted", existing.sonarqube.token_encrypted
                ),
                webhook_secret_encrypted=sonar_data.get(
                    "webhook_secret_encrypted", existing.sonarqube.webhook_secret_encrypted
                ),
                default_config=sonar_data.get("default_config", existing.sonarqube.default_config),
            )

        # Update Trivy
        if request.trivy:
            trivy_data = request.trivy.model_dump(exclude_none=True)
            existing.trivy = TrivySettings(
                server_url=trivy_data.get("server_url", existing.trivy.server_url),
                default_config=trivy_data.get("default_config", existing.trivy.default_config),
            )

        # Update Notifications
        if request.notifications:
            notif_data = request.notifications.model_dump(exclude_none=True)
            existing.notifications = NotificationSettings(
                email_enabled=notif_data.get("email_enabled", existing.notifications.email_enabled),
                email_recipients=notif_data.get(
                    "email_recipients", existing.notifications.email_recipients
                ),
            )

        # Save to database
        existing.mark_updated()
        self.repo.upsert_settings(existing)

        return self.get_settings()

    def get_decrypted_token(self, service: str) -> Optional[str]:
        """Get decrypted token for a service (for internal use by runners/tasks)."""
        db_settings = self.repo.get_settings()
        if not db_settings:
            # Fallback to ENV
            if service == "circleci":
                return app_config.CIRCLECI_TOKEN
            elif service == "travis":
                return app_config.TRAVIS_TOKEN
            elif service == "sonarqube":
                return app_config.SONAR_TOKEN
            return None

        if service == "circleci":
            return self._decrypt_token(db_settings.circleci.token_encrypted or "")
        elif service == "travis":
            return self._decrypt_token(db_settings.travis.token_encrypted or "")
        elif service == "sonarqube":
            return self._decrypt_token(db_settings.sonarqube.token_encrypted or "")
        return None

    def initialize_from_env(self) -> bool:
        """Initialize DB settings from ENV vars if not already exists.

        Called on app startup to ensure settings exist in DB.
        Returns True if initialization was performed, False if settings already exist.
        """
        existing = self.repo.get_settings()
        if existing:
            logger.info("Settings already initialized in DB")
            return False

        logger.info("Initializing settings from ENV vars...")

        # Create settings from ENV
        settings_entity = ApplicationSettings(
            circleci=CircleCISettings(
                base_url=app_config.CIRCLECI_BASE_URL,
                token_encrypted=self._encrypt_token(app_config.CIRCLECI_TOKEN or ""),
            ),
            travis=TravisCISettings(
                base_url=app_config.TRAVIS_BASE_URL,
                token_encrypted=self._encrypt_token(app_config.TRAVIS_TOKEN or ""),
            ),
            sonarqube=SonarQubeSettings(
                host_url=app_config.SONAR_HOST_URL,
                token_encrypted=self._encrypt_token(app_config.SONAR_TOKEN or ""),
                webhook_secret_encrypted=self._encrypt_token(
                    getattr(app_config, "SONAR_WEBHOOK_SECRET", "") or ""
                ),
                default_config=DEFAULT_SONARQUBE_CONFIG,
            ),
            trivy=TrivySettings(
                server_url=getattr(app_config, "TRIVY_SERVER_URL", None),
                default_config=DEFAULT_TRIVY_CONFIG,
            ),
            notifications=NotificationSettings(
                email_enabled=False,
                email_recipients="",
            ),
        )

        self.repo.upsert_settings(settings_entity)
        logger.info("Settings initialized from ENV vars successfully")
        return True
