"""Admin-only user management API endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from pymongo.database import Database

from app.database.mongo import get_db
from app.dtos.admin_user import (
    AdminUserResponse,
    AdminUserListResponse,
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
    AdminUserRoleUpdateRequest,
)
from app.middleware.require_admin import require_admin
from app.services.admin_user_service import AdminUserService

router = APIRouter(prefix="/admin/users", tags=["Admin - Users"])


@router.get(
    "/",
    response_model=AdminUserListResponse,
    response_model_by_alias=False,
)
def list_users(
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """List all users (Admin only). UC6: View User List"""
    service = AdminUserService(db)
    return service.list_users()


@router.post(
    "/",
    response_model=AdminUserResponse,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    payload: AdminUserCreateRequest,
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Create a new user (Admin only). UC1: Create User Account"""
    service = AdminUserService(db)
    return service.create_user(payload)


@router.get(
    "/{user_id}",
    response_model=AdminUserResponse,
    response_model_by_alias=False,
)
def get_user(
    user_id: str = Path(..., description="User ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Get user details (Admin only)."""
    service = AdminUserService(db)
    return service.get_user(user_id)


@router.patch(
    "/{user_id}",
    response_model=AdminUserResponse,
    response_model_by_alias=False,
)
def update_user(
    payload: AdminUserUpdateRequest,
    user_id: str = Path(..., description="User ID"),
    db: Database = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    """Update user profile (Admin only). UC3: Update User Profile"""
    service = AdminUserService(db)
    return service.update_user(user_id, payload)


@router.patch(
    "/{user_id}/role",
    response_model=AdminUserResponse,
    response_model_by_alias=False,
)
def update_user_role(
    payload: AdminUserRoleUpdateRequest,
    user_id: str = Path(..., description="User ID"),
    db: Database = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Assign/change user role (Admin only). UC2: Assign User Role"""
    service = AdminUserService(db)
    current_admin_id = str(admin["_id"])
    return service.update_user_role(user_id, payload.role, current_admin_id)


@router.delete(
    "/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_user(
    user_id: str = Path(..., description="User ID"),
    db: Database = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """Delete user account (Admin only). UC4: Delete User Account"""
    service = AdminUserService(db)
    current_admin_id = str(admin["_id"])
    service.delete_user(user_id, current_admin_id)
