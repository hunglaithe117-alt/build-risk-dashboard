import logging
from app.models.entities.imported_repository import ImportStatus, ImportSource
from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.dtos import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
    RepoSearchResponse,
)
from datetime import datetime, timezone
from app.repositories.available_repository import AvailableRepositoryRepository
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.services.github.github_client import (
    get_public_github_client,
    get_user_github_client,
)
from app.services.github.github_sync import sync_user_available_repos
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
            # Note: For public repositories found via search, available_repo might be None.
            # This is expected, and we will create the AvailableRepository record during ingestion.

            # Note: For public repositories found via search, available_repo might be None.
            # If so, we need to fetch it and create the AvailableRepository record.
            if not available_repo:
                try:
                    with get_public_github_client() as gh:
                        repo_data = gh.get_repository(payload.full_name)

                        # Create AvailableRepository record
                        new_available_repo = {
                            "user_id": ObjectId(user_id),
                            "full_name": payload.full_name,
                            "github_id": repo_data.get("id"),
                            "private": bool(repo_data.get("private")),
                            "html_url": repo_data.get("html_url"),
                            "description": repo_data.get("description"),
                            "default_branch": repo_data.get("default_branch", "main"),
                            "language": repo_data.get("language"),
                            "metadata": repo_data,
                            "installation_id": None,
                            "imported": False,
                            "created_at": datetime.now(timezone.utc),
                            "updated_at": datetime.now(timezone.utc),
                        }
                        self.db.available_repositories.insert_one(new_available_repo)
                        available_repo = new_available_repo

                except Exception as e:
                    logger.error(
                        f"Failed to fetch public repo details for {payload.full_name}: {e}"
                    )
                    # If we can't fetch it, we can't import it properly.
                    continue

            # We allow re-importing to retry failed imports or update settings.
            # The upsert_repository below will handle updates.
            # Main flow repos are marked with import_source = "main"

            try:
                repo_doc = self.repo_repo.upsert_repository(
                    query={
                        "user_id": ObjectId(target_user_id),
                        "provider": payload.provider,
                        "full_name": payload.full_name,
                        "import_source": ImportSource.MAIN.value,  # Main flow only
                    },
                    data={
                        "installation_id": installation_id,
                        "test_frameworks": payload.test_frameworks,
                        "source_languages": payload.source_languages,
                        "ci_provider": payload.ci_provider,
                        "import_status": ImportStatus.QUEUED.value,
                        "import_source": ImportSource.MAIN.value,
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
            logger.error(f"Failed to sync repositories: {e}")

        items = self.available_repo_repo.discover_available_repositories(
            user_id=user_id, q=None, limit=limit
        )
        return RepoSuggestionListResponse(items=items)

    def list_repositories(
        self, user_id: str, skip: int, limit: int, q: Optional[str] = None
    ) -> RepoListResponse:
        """List tracked repositories with pagination."""
        query = {}
        if q:
            query["full_name"] = {"$regex": q, "$options": "i"}

        repos, total = self.repo_repo.list_by_user(
            user_id, skip=skip, limit=limit, query=query
        )
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

    def search_repositories(self, user_id: str, q: str | None) -> RepoSearchResponse:
        """Search for repositories (both private installed and public GitHub)."""
        # 1. Search private installed repos (DB)
        private_matches = self.available_repo_repo.discover_available_repositories(
            user_id=user_id, q=q, limit=50
        )

        public_matches = []
        # 2. Search public repos (GitHub API) - only if query is long enough
        if q and len(q) >= 3:
            try:
                with get_user_github_client(self.db, user_id) as gh:
                    # Search for public repos matching the query
                    # We use 'in:name,description' and 'is:public' to narrow down
                    query = f"{q} in:name,description is:public"
                    results = gh.search_repositories(query, per_page=10)

                    for repo in results:
                        public_matches.append(
                            {
                                "full_name": repo["full_name"],
                                "description": repo.get("description"),
                                "default_branch": repo.get("default_branch"),
                                "private": False,
                                "owner": repo["owner"]["login"],
                                "html_url": repo["html_url"],
                                "installation_id": None,
                            }
                        )
            except Exception as e:
                logger.error(f"Failed to search public repos: {e}")

        return RepoSearchResponse(
            private_matches=private_matches, public_matches=public_matches
        )

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

    def trigger_sync(self, repo_id: str, user_id: str):
        """Trigger a full sync for a specific repository."""
        repo_doc = self.repo_repo.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        if repo_doc.installation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lazy sync is not available for App-installed repositories.",
            )

        # Update status to queued/importing
        self.repo_repo.update_repository(
            repo_id, {"import_status": ImportStatus.QUEUED.value}
        )

        # Trigger import task
        import_repo.delay(
            user_id=user_id,
            full_name=repo_doc.full_name,
            installation_id=repo_doc.installation_id,
            provider=repo_doc.provider,
            test_frameworks=repo_doc.test_frameworks,
            source_languages=repo_doc.source_languages,
            ci_provider=repo_doc.ci_provider,
        )

        return {"status": "queued"}
