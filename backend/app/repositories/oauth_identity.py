"""OAuth identity repository for database operations"""

from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

from pymongo.database import Database

from .base import BaseRepository
from .user import UserRepository


class OAuthIdentityRepository(BaseRepository):
    """Repository for OAuth identity entities"""

    def __init__(self, db: Database):
        super().__init__(db, "oauth_identities")
        self.user_repo = UserRepository(db)

    def find_by_provider_and_external_id(
        self, provider: str, external_user_id: str
    ) -> Optional[Dict]:
        """Find an identity by provider and external user ID"""
        return self.find_one(
            {"provider": provider, "external_user_id": external_user_id}
        )

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
    ) -> Tuple[Dict, Dict]:
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
            self.update_one(existing_identity["_id"], identity_updates)

            # Update user if needed
            user_doc = self.user_repo.find_by_id(existing_identity["user_id"])
            if not user_doc:
                raise ValueError("User referenced by identity not found")

            user_updates = {}
            if email and user_doc.get("email") != email:
                user_updates["email"] = email
            if name and user_doc.get("name") != name:
                user_updates["name"] = name

            if user_updates:
                self.user_repo.update_one(user_doc["_id"], user_updates)
                user_doc.update(user_updates)

            identity_doc = self.find_by_id(existing_identity["_id"])
            return user_doc, identity_doc

        # Create new user and identity
        user_doc = self.user_repo.create_user(email, name, role="user")

        identity_doc = {
            "user_id": user_doc["_id"],
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
