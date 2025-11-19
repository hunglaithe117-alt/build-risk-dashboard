"""Authentication middleware and dependencies for FastAPI."""
from __future__ import annotations

from typing import Optional

from bson import ObjectId
from fastapi import Cookie, Depends, HTTPException, Header, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.services.auth import decode_access_token


async def get_current_user_id(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> str:
    """Extract and validate user ID from JWT token.
    
    Checks for token in:
    1. Cookie (access_token)
    2. Authorization header (Bearer token)
    
    Args:
        access_token: JWT token from cookie
        authorization: Authorization header value
    
    Returns:
        User ID string
    
    Raises:
        HTTPException: If no valid token is found
    """
    token = None
    
    # Try to get token from cookie first
    if access_token:
        token = access_token
    # Then try Authorization header
    elif authorization and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please login.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Decode and validate token
    try:
        payload = decode_access_token(token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {str(e)}"
        )


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: Database = Depends(get_db),
) -> dict:
    """Get the current authenticated user from the database.
    
    Args:
        user_id: User ID from JWT token
        db: MongoDB database instance
    
    Returns:
        User document from database
    
    Raises:
        HTTPException: If user is not found
    """
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate user: {str(e)}"
        )


async def get_current_user_optional(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
    db: Database = Depends(get_db),
) -> Optional[dict]:
    """Get current user if authenticated, otherwise return None.
    
    Useful for endpoints that work both authenticated and unauthenticated.
    
    Args:
        access_token: JWT token from cookie
        authorization: Authorization header value
        db: MongoDB database instance
    
    Returns:
        User document if authenticated, None otherwise
    """
    try:
        user_id = await get_current_user_id(access_token, authorization)
        user = db.users.find_one({"_id": ObjectId(user_id)})
        return user
    except HTTPException:
        return None
