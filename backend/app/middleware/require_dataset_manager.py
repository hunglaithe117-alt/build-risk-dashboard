"""Dataset manager role requirement middleware for FastAPI.

This middleware allows only the admin role to perform dataset management
operations including:
- Upload datasets
- Create/delete/cancel dataset versions
- Start/cancel integration scans
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from app.middleware.auth import get_current_user


async def require_dataset_manager(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Dependency that requires dataset manager access (admin only).

    Admin has full dataset enrichment capabilities:
    - Upload datasets
    - Create/delete/cancel versions
    - Start/cancel scans
    - Export data

    Raises:
        HTTPException: 403 Forbidden if user is not an admin

    Returns:
        The user dict if they have dataset manager access
    """
    user_role = current_user.get("role")
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dataset manager access required. Admins can perform this action.",
        )
    return current_user


async def require_dataset_viewer(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Dependency that requires dataset viewer access (admin only).

    This is for read-only dataset operations that only admins can access.

    Raises:
        HTTPException: 403 Forbidden if user is not an admin

    Returns:
        The user dict if they have dataset viewer access
    """
    user_role = current_user.get("role")
    if user_role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dataset viewer access required. Only admins can view datasets.",
        )
    return current_user
