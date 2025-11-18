"""Authentication DTOs"""

from typing import Dict, Optional

from pydantic import BaseModel

from .user import OAuthIdentityResponse, UserResponse


class GithubLoginRequest(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: Optional[int] = None
    scope: Optional[str] = None


class UserLoginResponse(BaseModel):
    user: UserResponse
    identity: OAuthIdentityResponse


class AuthVerifyResponse(BaseModel):
    authenticated: bool
    reason: Optional[str] = None
    user: Optional[Dict[str, Optional[str]]] = None
    github: Optional[Dict[str, Optional[str]]] = None
