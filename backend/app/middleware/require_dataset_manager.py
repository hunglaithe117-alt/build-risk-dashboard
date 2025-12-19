"""Dataset manager role requirement middleware for FastAPI.

This middleware allows both admin and guest roles to perform dataset management
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
    Dependency that requires dataset manager access (admin or guest).

    Guest has full dataset enrichment capabilities:
    - Upload datasets
    - Create/delete/cancel versions
    - Start/cancel scans
    - Export data

    Raises:
        HTTPException: 403 Forbidden if user is not an admin or guest

    Returns:
        The user dict if they have dataset manager access
    """
    user_role = current_user.get("role")
    if user_role not in ("admin", "guest"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dataset manager access required. Admins and guests can perform this action.",
        )
    return current_user


async def require_dataset_viewer(
    current_user: dict = Depends(get_current_user),
) -> dict:
    """
    Dependency that requires dataset viewer access (admin or guest).

    This is for read-only dataset operations that both admin and guest can access.

    Raises:
        HTTPException: 403 Forbidden if user is not an admin or guest

    Returns:
        The user dict if they have dataset viewer access
    """
    user_role = current_user.get("role")
    if user_role not in ("admin", "guest"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dataset viewer access required. Only admins and guests can view datasets.",
        )
    return current_user
