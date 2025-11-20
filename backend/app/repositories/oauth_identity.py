"""OAuth identity repository for database operations"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from pymongo.database import Database

from app.models.entities.oauth_identity import OAuthIdentity
from app.models.entities.user import User
from .base import BaseRepository
from .user import UserRepository


class OAuthIdentityRepository(BaseRepository[OAuthIdentity]):

    def __init__(self, db: Database):
        super().__init__(db, "oauth_identities", OAuthIdentity)
        self.user_repo = UserRepository(db)

    def find_by_provider_and_external_id(
        self, provider: str, external_user_id: str
    ) -> Optional[OAuthIdentity]:
        return self.find_one(
            {"provider": provider, "external_user_id": external_user_id}
        )

    def find_by_user_id_and_provider(
        self, user_id, provider: str
    ) -> Optional[OAuthIdentity]:
        return self.find_one({"user_id": user_id, "provider": provider})

    def mark_token_invalid(self, identity_id, reason: str = "invalid") -> None:
        self.update_one(
            identity_id,
            {
                "token_status": "invalid",
                "token_invalid_reason": reason,
                "token_invalidated_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            },
        )

    def update_token(
        self,
        identity_id,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
    ) -> None:
        """Update token information"""
        updates = {
            "access_token": access_token,
            "token_status": "valid",
            "updated_at": datetime.now(timezone.utc),
        }
        if refresh_token is not None:
            updates["refresh_token"] = refresh_token
        if token_expires_at is not None:
            updates["token_expires_at"] = token_expires_at

        self.update_one(identity_id, updates)

    def upsert_github_identity(
        self,
        *,
        github_user_id: str,
        email: str,
        name: Optional[str],
        access_token: str,
        refresh_token: Optional[str],
        token_expires_at: Optional[datetime],
        scopes: Optional[str],
        account_login: Optional[str] = None,
        account_name: Optional[str] = None,
        account_avatar_url: Optional[str] = None,
        connected_at: Optional[datetime] = None,
    ) -> Tuple[User, OAuthIdentity]:
        """Upsert a GitHub identity and associated user"""
        provider = "github"
        existing_identity = self.find_by_provider_and_external_id(
            provider, github_user_id
        )

        now = datetime.now(timezone.utc)

        if existing_identity:
            # Update existing identity
            identity_updates = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_expires_at": token_expires_at,
                "scopes": scopes,
                "updated_at": now,
                "account_login": account_login,
                "account_name": account_name,
                "account_avatar_url": account_avatar_url,
                "connected_at": connected_at,
            }
            self.update_one(existing_identity.id, identity_updates)

            # Update user if needed
            user_doc = self.user_repo.find_by_id(existing_identity.user_id)
            if not user_doc:
                raise ValueError("User referenced by identity not found")

            user_updates = {}
            if email and user_doc.email != email:
                user_updates["email"] = email
            if name and user_doc.name != name:
                user_updates["name"] = name

            if user_updates:
                self.user_repo.update_one(user_doc.id, user_updates)
                user_doc = self.user_repo.find_by_id(user_doc.id)

            identity_doc = self.find_by_id(existing_identity.id)
            return user_doc, identity_doc

        # Create new user and identity
        user_doc = self.user_repo.create_user(email, name, role="user")

        identity_doc = {
            "user_id": user_doc.id,
            "provider": provider,
            "external_user_id": github_user_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_expires_at": token_expires_at,
            "scopes": scopes,
            "account_login": account_login,
            "account_name": account_name,
            "account_avatar_url": account_avatar_url,
            "connected_at": connected_at,
            "created_at": now,
        }
        identity_doc = self.insert_one(identity_doc)

        return user_doc, identity_doc
