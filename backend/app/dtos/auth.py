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
    github_connected: Optional[bool] = None
    app_installed: Optional[bool] = None
    reason: Optional[str] = None
    user: Optional[Dict[str, Optional[str]]] = None
    github: Optional[Dict[str, Optional[str]]] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class GitHubInfo(BaseModel):
    connected: bool
    login: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
    token_status: Optional[str] = None
    scopes: Optional[list[str]] = None


class UserDetailResponse(BaseModel):
    id: str
    email: Optional[str] = None
    name: Optional[str] = None
    role: str = "user"
    created_at: Optional[str] = None
    github: GitHubInfo
