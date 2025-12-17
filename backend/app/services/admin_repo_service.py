"""Admin Repository Access Control Service."""

from __future__ import annotations

from typing import List, Literal, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos.admin_repo import (
    AdminRepoListResponse,
    RepoAccessResponse,
    RepoAccessSummary,
)
from app.dtos.admin_user import AdminUserResponse
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.user import UserRepository


class AdminRepoService:
    """Service for admin repository access control operations."""

    def __init__(self, db: Database):
        self.db = db
        self.repo_config = ModelRepoConfigRepository(db)
        self.user_repo = UserRepository(db)

    def _to_user_response(self, user) -> AdminUserResponse:
        """Convert User entity to AdminUserResponse."""
        return AdminUserResponse(
            _id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at,
        )

    def list_repos(
        self,
        skip: int = 0,
        limit: int = 50,
        visibility: Optional[str] = None,
    ) -> AdminRepoListResponse:
        """List all repositories with access info (Admin only)."""
        # Build query
        query = {"is_deleted": {"$ne": True}}
        if visibility:
            query["visibility"] = visibility

        # Get repos
        cursor = self.repo_config.collection.find(query).skip(skip).limit(limit)
        total = self.repo_config.collection.count_documents(query)

        items = []
        for doc in cursor:
            items.append(
                RepoAccessSummary(
                    _id=str(doc["_id"]),
                    full_name=doc.get("full_name", "Unknown"),
                    visibility=doc.get("visibility", "public"),
                    granted_user_count=len(doc.get("granted_user_ids", [])),
                    owner_id=str(doc.get("user_id", "")),
                )
            )

        return AdminRepoListResponse(items=items, total=total)

    def get_repo_access(self, repo_id: str) -> RepoAccessResponse:
        """Get repository access details (UC5: Grant Repository Access)."""
        repo = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found",
            )

        # Get granted users
        granted_user_ids = getattr(repo, "granted_user_ids", [])
        granted_users = []
        for uid in granted_user_ids:
            user = self.user_repo.find_by_id(uid)
            if user:
                granted_users.append(self._to_user_response(user))

        return RepoAccessResponse(
            repo_id=str(repo.id),
            full_name=repo.full_name,
            visibility=getattr(repo, "visibility", "public"),
            granted_users=granted_users,
        )

    def grant_access(self, repo_id: str, user_ids: List[str]) -> RepoAccessResponse:
        """Grant users access to a repository (UC5: Grant Repository Access)."""
        repo = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found",
            )

        # Validate user IDs exist
        new_user_ids = []
        for uid_str in user_ids:
            try:
                uid = ObjectId(uid_str)
                user = self.user_repo.find_by_id(uid)
                if user:
                    new_user_ids.append(uid)
            except Exception:
                pass  # Skip invalid IDs

        if not new_user_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid user IDs provided",
            )

        # Add to granted_user_ids (using $addToSet to avoid duplicates)
        self.repo_config.collection.update_one(
            {"_id": ObjectId(repo_id)},
            {"$addToSet": {"granted_user_ids": {"$each": new_user_ids}}},
        )

        return self.get_repo_access(repo_id)

    def revoke_access(self, repo_id: str, user_ids: List[str]) -> RepoAccessResponse:
        """Revoke users' access from a repository (UC5: Grant Repository Access)."""
        repo = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found",
            )

        # Convert to ObjectIds
        user_ids_to_remove = [ObjectId(uid) for uid in user_ids]

        # Remove from granted_user_ids
        self.repo_config.collection.update_one(
            {"_id": ObjectId(repo_id)},
            {"$pull": {"granted_user_ids": {"$in": user_ids_to_remove}}},
        )

        return self.get_repo_access(repo_id)

    def update_visibility(
        self, repo_id: str, visibility: Literal["public", "private"]
    ) -> RepoAccessResponse:
        """Update repository visibility (UC5: Grant Repository Access)."""
        repo = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Repository not found",
            )

        # Update visibility
        self.repo_config.collection.update_one(
            {"_id": ObjectId(repo_id)},
            {"$set": {"visibility": visibility}},
        )

        return self.get_repo_access(repo_id)
