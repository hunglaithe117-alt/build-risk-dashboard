"""Admin role requirement middleware for FastAPI."""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.middleware.auth import get_current_user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """
    Dependency that requires the current user to have admin role.

    NOTE: Temporarily disabled - all authenticated users have access.
    TODO: Re-enable when ready to enforce RBAC.

    Raises:
        HTTPException: 403 Forbidden if user is not an admin

    Returns:
        The user dict if they are an admin
    """
    # Temporarily disabled - allow all authenticated users
    # Uncomment below to enforce admin check:
    # if user.get("role") != "admin":
    #     raise HTTPException(
    #         status_code=status.HTTP_403_FORBIDDEN,
    #         detail="Admin access required. You don't have permission to perform this action.",
    #     )
    return user


async def require_admin_or_self(
    target_user_id: str, user: dict = Depends(get_current_user)
) -> dict:
    """
    Dependency that requires admin or the user themselves.
    Useful for profile update endpoints.
    """
    user_id = str(user.get("_id"))
    if user.get("role") != "admin" and user_id != target_user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this resource.",
        )
    return user
