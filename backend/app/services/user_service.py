"""User account service using repository pattern"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pymongo.database import Database

from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import UserResponse
from app.entities.oauth_identity import OAuthIdentity
from app.entities.user import User
from app.repositories.oauth_identity import OAuthIdentityRepository
from app.repositories.user import UserRepository

PROVIDER_GITHUB = "github"


def upsert_github_identity(
    db: Database,
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
    oauth_repo = OAuthIdentityRepository(db)
    return oauth_repo.upsert_github_identity(
        github_user_id=github_user_id,
        email=email,
        name=name,
        access_token=access_token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        scopes=scopes,
        account_login=account_login,
        account_name=account_name,
        account_avatar_url=account_avatar_url,
        connected_at=connected_at,
    )


class UserService:
    def __init__(self, db: Database):
        self.db = db

    def list_users(self) -> List[UserResponse]:
        """List all users"""
        user_repo = UserRepository(self.db)
        documents = user_repo.list_all()
        return [UserResponse.model_validate(doc) for doc in documents]

    def get_current_user(self) -> UserResponse:
        # Find an OAuth identity for GitHub and use the linked user document.
        identity = self.db.oauth_identities.find_one({"provider": PROVIDER_GITHUB})
        if not identity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No user is currently logged in.",
            )

        user_doc = self.db.users.find_one({"_id": identity["user_id"]})

        if user_doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No user found for the current GitHub connection.",
            )

        return UserResponse.model_validate(user_doc)
