"""User account service using repository pattern"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from pymongo.database import Database

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
) -> Tuple[Dict[str, object], Dict[str, object]]:
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


def list_users(db: Database) -> List[Dict[str, object]]:
    """List all users"""
    user_repo = UserRepository(db)
    return user_repo.list_all()
