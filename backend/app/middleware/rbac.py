"""
RBAC (Role-Based Access Control) Middleware for FastAPI.

This module provides a centralized permission system with:
- Permission enum for fine-grained access control
- Role-to-permissions mapping
- Dependency factories for route protection
"""

from __future__ import annotations

from enum import Enum
from typing import Set

from fastapi import Depends, HTTPException, status

from app.middleware.auth import get_current_user


class Permission(str, Enum):
    """Available permissions in the system."""

    # Admin-only permissions
    ADMIN_FULL = "admin:full"
    MANAGE_USERS = "manage:users"
    MANAGE_REPOS = "manage:repos"
    DELETE_DATA = "delete:data"

    # Viewer permissions (Admin + User) - Repos/Builds
    VIEW_DASHBOARD = "view:dashboard"
    VIEW_REPOS = "view:repos"
    VIEW_BUILDS = "view:builds"

    # Dataset permissions (Admin + Guest)
    VIEW_DATASETS = "view:datasets"  # Includes versions & scans
    MANAGE_DATASETS = "manage:datasets"
    START_SCANS = "start:scans"
    EXPORT_DATA = "export:data"

    # User's own dashboard
    VIEW_OWN_DASHBOARD = "view:own_dashboard"

    # Notification permissions (all authenticated users)
    VIEW_NOTIFICATIONS = "view:notifications"
    MANAGE_NOTIFICATIONS = "manage:notifications"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[str, Set[Permission]] = {
    "admin": {
        # Admin has ALL permissions
        Permission.ADMIN_FULL,
        Permission.MANAGE_USERS,
        Permission.MANAGE_REPOS,
        Permission.DELETE_DATA,
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_REPOS,
        Permission.VIEW_BUILDS,
        Permission.VIEW_DATASETS,
        Permission.MANAGE_DATASETS,
        Permission.START_SCANS,
        Permission.EXPORT_DATA,
        Permission.VIEW_OWN_DASHBOARD,
        Permission.VIEW_NOTIFICATIONS,
        Permission.MANAGE_NOTIFICATIONS,
    },
    "user": {
        # User: repos họ thuộc về + dashboard + notifications
        # VIEW_REPOS filtered by github_accessible_repos in repository layer
        Permission.VIEW_DASHBOARD,
        Permission.VIEW_REPOS,
        Permission.VIEW_BUILDS,
        Permission.VIEW_OWN_DASHBOARD,
        Permission.VIEW_NOTIFICATIONS,
        Permission.MANAGE_NOTIFICATIONS,
    },
    "guest": {
        # Guest: CHỈ datasets + own dashboard + notifications
        # KHÔNG có VIEW_REPOS, VIEW_BUILDS
        Permission.VIEW_DATASETS,
        Permission.MANAGE_DATASETS,
        Permission.START_SCANS,
        Permission.EXPORT_DATA,
        Permission.VIEW_OWN_DASHBOARD,
        Permission.VIEW_NOTIFICATIONS,
        Permission.MANAGE_NOTIFICATIONS,
    },
}


def get_user_permissions(role: str) -> Set[Permission]:
    """Get all permissions for a given role."""
    return ROLE_PERMISSIONS.get(role, set())


def has_permission(role: str, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in get_user_permissions(role)


def has_any_permission(role: str, permissions: Set[Permission]) -> bool:
    """Check if a role has any of the given permissions."""
    user_perms = get_user_permissions(role)
    return bool(user_perms & permissions)


def has_all_permissions(role: str, permissions: Set[Permission]) -> bool:
    """Check if a role has all of the given permissions."""
    user_perms = get_user_permissions(role)
    return permissions.issubset(user_perms)


class RequirePermission:
    """
    Dependency class for requiring specific permissions.

    Usage:
        @router.get("/admin-only")
        def admin_endpoint(user: dict = Depends(RequirePermission(Permission.ADMIN_FULL))):
            ...

        @router.get("/viewer")
        def viewer_endpoint(user: dict = Depends(RequirePermission(Permission.VIEW_DATASETS))):
            ...
    """

    def __init__(self, *permissions: Permission, require_all: bool = False):
        """
        Initialize permission requirement.

        Args:
            *permissions: One or more permissions to check
            require_all: If True, user must have ALL permissions. If False, user needs ANY.
        """
        self.permissions = set(permissions)
        self.require_all = require_all

    async def __call__(self, user: dict = Depends(get_current_user)) -> dict:
        """Check if user has required permissions."""
        role = user.get("role", "user")

        if self.require_all:
            has_access = has_all_permissions(role, self.permissions)
        else:
            has_access = has_any_permission(role, self.permissions)

        if not has_access:
            perm_names = ", ".join(p.value for p in self.permissions)
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {perm_names}",
            )

        return user


# Convenience dependency instances for common permission patterns
require_admin = RequirePermission(Permission.ADMIN_FULL)
require_viewer = RequirePermission(Permission.VIEW_DATASETS, Permission.VIEW_REPOS)
require_manage_users = RequirePermission(Permission.MANAGE_USERS)
require_manage_repos = RequirePermission(Permission.MANAGE_REPOS)
require_manage_datasets = RequirePermission(Permission.MANAGE_DATASETS)
require_start_scans = RequirePermission(Permission.START_SCANS)
require_export = RequirePermission(Permission.EXPORT_DATA)


# For backward compatibility - alias to old middleware names
async def require_admin_legacy(user: dict = Depends(get_current_user)) -> dict:
    """
    Legacy dependency that requires admin role.
    Prefer using RequirePermission(Permission.ADMIN_FULL) instead.
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required.",
        )
    return user
