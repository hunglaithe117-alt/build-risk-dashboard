import logging
from app.models.entities.imported_repository import ImportStatus
from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from pymongo.database import Database

from app.dtos import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
)
from app.repositories.available_repository import AvailableRepositoryRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.services.github.github_client import get_app_github_client
from app.services.github.github_sync import sync_user_available_repos
from app.services.github.exceptions import GithubConfigurationError
from app.tasks.ingestion import import_repo


logger = logging.getLogger(__name__)


def _serialize_repo(repo_doc) -> RepoResponse:
    return RepoResponse.model_validate(repo_doc)


def _serialize_repo_detail(repo_doc) -> RepoDetailResponse:
    return RepoDetailResponse.model_validate(repo_doc)


class RepositoryService:
    def __init__(self, db: Database):
        self.db = db
        self.repo_repo = ImportedRepositoryRepository(db)
        self.available_repo_repo = AvailableRepositoryRepository(db)

    def bulk_import_repositories(
        self, user_id: str, payloads: List[RepoImportRequest]
    ) -> List[RepoResponse]:
        results = []

        full_names = [p.full_name for p in payloads]
        available_repos = list(
            self.db.available_repositories.find(
                {
                    "user_id": ObjectId(user_id),
                    "full_name": {"$in": full_names},
                    "imported": {"$ne": True},
                }
            )
        )
        available_map = {r["full_name"]: r for r in available_repos}

        for payload in payloads:
            target_user_id = user_id

            available_repo = available_map.get(payload.full_name)
            installation_id = payload.installation_id

            if available_repo and available_repo.get("installation_id"):
                installation_id = available_repo.get("installation_id")

            if not installation_id and self.repo_repo.find_one(
                {
                    "user_id": ObjectId(target_user_id),
                    "provider": payload.provider,
                    "full_name": payload.full_name,
                }
            ):
                # Skip or log
                continue

            try:
                repo_doc = self.repo_repo.upsert_repository(
                    query={
                        "user_id": ObjectId(target_user_id),
                        "provider": payload.provider,
                        "full_name": payload.full_name,
                    },
                    data={
                        "installation_id": installation_id,
                        "test_frameworks": payload.test_frameworks,
                        "source_languages": payload.source_languages,
                        "ci_provider": payload.ci_provider,
                        "import_status": ImportStatus.QUEUED.value,
                    },
                )

                # Trigger async import
                import_repo.delay(
                    user_id=target_user_id,
                    full_name=payload.full_name,
                    installation_id=installation_id,
                    provider=payload.provider,
                    test_frameworks=payload.test_frameworks,
                    source_languages=payload.source_languages,
                    ci_provider=payload.ci_provider,
                )

                results.append(repo_doc)

            except Exception as e:
                # Log error and continue
                logger.error(f"Failed to import {payload.full_name}: {e}")
                continue

        return [_serialize_repo(doc) for doc in results]

    def sync_repositories(self, user_id: str, limit: int) -> RepoSuggestionListResponse:
        """Sync available repositories from GitHub App Installations."""
        try:
            sync_user_available_repos(self.db, user_id)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to sync repositories: {str(e)}",
            )

        items = self.available_repo_repo.discover_available_repositories(
            user_id=user_id, q=None, limit=limit
        )
        return RepoSuggestionListResponse(items=items)

    def list_repositories(
        self, user_id: str, skip: int, limit: int
    ) -> RepoListResponse:
        """List tracked repositories with pagination."""
        repos, total = self.repo_repo.list_by_user(user_id, skip=skip, limit=limit)
        return RepoListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=[_serialize_repo(repo) for repo in repos],
        )

    def discover_repositories(
        self, user_id: str, q: str | None, limit: int
    ) -> RepoSuggestionListResponse:
        """List available repositories."""
        items = self.available_repo_repo.discover_available_repositories(
            user_id=user_id, q=q, limit=limit
        )
        return RepoSuggestionListResponse(items=items)

    def get_repository_detail(
        self, repo_id: str, current_user: dict
    ) -> RepoDetailResponse:
        repo_doc = self.repo_repo.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Verify user owns this repository
        repo_user_id = str(repo_doc.user_id)
        current_user_id = str(current_user["_id"])
        if repo_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this repository",
            )

        return _serialize_repo_detail(repo_doc)

    def update_repository_settings(
        self, repo_id: str, payload: RepoUpdateRequest, current_user: dict
    ) -> RepoDetailResponse:
        repo_doc = self.repo_repo.get_repository(repo_id)
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Verify user owns this repository
        repo_user_id = str(repo_doc.user_id)
        current_user_id = str(current_user["_id"])
        if repo_user_id != current_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to update this repository",
            )

        updates = payload.model_dump(exclude_unset=True)

        if not updates:
            updated = repo_doc
        else:
            updated = self.repo_repo.update_repository(repo_id, updates)
            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
                )

        return _serialize_repo_detail(updated)
