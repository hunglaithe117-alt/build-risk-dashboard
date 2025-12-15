"""Authentication middleware and dependencies for FastAPI."""

from __future__ import annotations

from typing import Optional

from bson import ObjectId
from fastapi import Cookie, Depends, HTTPException, Header, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.services.auth_service import decode_access_token


async def get_current_user_id(
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> str:
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
                detail="Invalid authentication credentials",
            )
        return user_id
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(e)}"
        )


async def get_current_user(
    user_id: str = Depends(get_current_user_id),
    db: Database = Depends(get_db),
) -> dict:
    try:
        user = db.users.find_one({"_id": ObjectId(user_id)})
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate user: {str(e)}",
        )
