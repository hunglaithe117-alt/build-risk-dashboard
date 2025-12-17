"""Admin User Management Service."""

from __future__ import annotations

from typing import List

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos.admin_user import (
    AdminUserResponse,
    AdminUserListResponse,
    AdminUserCreateRequest,
    AdminUserUpdateRequest,
)
from app.repositories.user import UserRepository


class AdminUserService:
    """Service for admin user management operations."""

    def __init__(self, db: Database):
        self.db = db
        self.user_repo = UserRepository(db)

    def _to_response(self, user) -> AdminUserResponse:
        """Convert User entity to AdminUserResponse."""
        return AdminUserResponse(
            _id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at,
        )

    def list_users(self) -> AdminUserListResponse:
        """List all users (UC6: View User List)."""
        users = self.user_repo.list_all()
        return AdminUserListResponse(
            items=[self._to_response(u) for u in users],
            total=len(users),
        )

    def get_user(self, user_id: str) -> AdminUserResponse:
        """Get user details by ID."""
        user = self.user_repo.find_by_id(ObjectId(user_id))
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return self._to_response(user)

    def create_user(self, payload: AdminUserCreateRequest) -> AdminUserResponse:
        """Create a new user (UC1: Create User Account)."""
        # Check if user already exists
        existing = self.user_repo.find_by_email(payload.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"User with email {payload.email} already exists",
            )

        user = self.user_repo.create_user(
            email=payload.email,
            name=payload.name,
            role=payload.role,
        )
        return self._to_response(user)

    def update_user(
        self, user_id: str, payload: AdminUserUpdateRequest
    ) -> AdminUserResponse:
        """Update user profile (UC3: Update User Profile)."""
        # Build updates dict excluding None values
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        user = self.user_repo.update_user(user_id, updates)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return self._to_response(user)

    def update_user_role(
        self, user_id: str, new_role: str, current_admin_id: str
    ) -> AdminUserResponse:
        """Assign/change user role (UC2: Assign User Role)."""
        # Prevent admin from demoting themselves if they're the last admin
        if user_id == current_admin_id and new_role != "admin":
            admin_count = self.user_repo.count_admins()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot demote the last admin. Assign another admin first.",
                )

        user = self.user_repo.update_role(user_id, new_role)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return self._to_response(user)

    def delete_user(self, user_id: str, current_admin_id: str) -> None:
        """Delete user account (UC4: Delete User Account)."""
        # Prevent admin from deleting themselves
        if user_id == current_admin_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account",
            )

        # Check if this would leave no admins
        user = self.user_repo.find_by_id(ObjectId(user_id))
        if user and user.role == "admin":
            admin_count = self.user_repo.count_admins()
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot delete the last admin",
                )

        success = self.user_repo.delete_user(user_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Also clean up OAuth identities for this user
        self.db.oauth_identities.delete_many({"user_id": ObjectId(user_id)})
