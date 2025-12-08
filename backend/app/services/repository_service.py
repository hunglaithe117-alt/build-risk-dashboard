import logging
from app.entities.imported_repository import ImportStatus
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
from app.repositories.imported_repository import ImportedRepositoryRepository
from app.repositories.dataset_template_repository import DatasetTemplateRepository
from app.services.github.github_client import (
    get_public_github_client,
    get_user_github_client,
)
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
        self.template_repo = DatasetTemplateRepository(db)

    def _resolve_feature_names(self, payload: RepoImportRequest) -> Optional[List[str]]:
        """Resolve feature names from template_id or use feature_names directly."""
        if payload.template_id:
            template = self.template_repo.find_by_id(ObjectId(payload.template_id))
            if template:
                return template.feature_names
        return payload.feature_names  # May be None

    def bulk_import_repositories(
        self, user_id: str, payloads: List[RepoImportRequest]
    ) -> List[RepoResponse]:
        results = []

        for payload in payloads:
            target_user_id = user_id
            installation_id = payload.installation_id

            # We allow re-importing to retry failed imports or update settings.
            # The upsert_repository below will handle updates.

            try:
                # Resolve feature names from template or use feature_ids directly
                resolved_features = self._resolve_feature_names(payload)

                # Note: We store feature names directly now, not ObjectIds
                # This aligns with code-defined registry approach

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
                        "ci_provider": payload.ci_provider or "github_actions",
                        "import_status": ImportStatus.QUEUED.value,
                        "requested_feature_names": resolved_features,
                        "max_builds_to_ingest": payload.max_builds,
                        "since_days": payload.since_days,
                        "only_with_logs": payload.only_with_logs,
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
                    ci_provider=payload.ci_provider or "github_actions",
                    feature_names=resolved_features,
                    max_builds=payload.max_builds,
                    since_days=payload.since_days,
                    only_with_logs=payload.only_with_logs,
                )

                results.append(repo_doc)

            except Exception as e:
                # Log error and continue
                logger.error(f"Failed to import {payload.full_name}: {e}")
                continue

        return [_serialize_repo(doc) for doc in results]

    def sync_repositories(self, user_id: str, limit: int) -> RepoSuggestionListResponse:
        """
        Fetch repositories accessible to the user directly from GitHub (no cache).
        Uses the user's GitHub token to list repos.
        """
        items: List[dict] = []
        try:
            with get_user_github_client(self.db, user_id) as gh:
                repos = gh._rest_request(
                    "GET",
                    "/user/repos",
                    params={"per_page": min(limit, 10), "sort": "full_name"},
                )
                for repo in repos:
                    full_name = repo.get("full_name")
                    if not full_name:
                        continue
                    items.append(
                        {
                            "full_name": full_name,
                            "description": repo.get("description"),
                            "default_branch": repo.get("default_branch"),
                            "private": bool(repo.get("private")),
                            "owner": repo.get("owner", {}).get("login"),
                            "installation_id": None,  # Not cached; resolved at import
                            "html_url": repo.get("html_url"),
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to fetch user repos from GitHub: {e}")

        return RepoSuggestionListResponse(items=items[:limit])

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
        """List available repositories (directly from GitHub)."""
        return self.sync_repositories(user_id, limit)

    def search_repositories(self, user_id: str, q: str | None) -> RepoSearchResponse:
        """Search for repositories directly against GitHub."""
        private_matches: List[dict] = []
        public_matches: List[dict] = []

        if not q or len(q) < 1:
            return RepoSearchResponse(private_matches=[], public_matches=[])

        try:
            with get_user_github_client(self.db, user_id) as gh:
                # Authenticated search returns both public and accessible private repos.
                results = gh.search_repositories(q, per_page=10)
                for repo in results:
                    entry = {
                        "full_name": repo.get("full_name"),
                        "description": repo.get("description"),
                        "default_branch": repo.get("default_branch"),
                        "private": bool(repo.get("private")),
                        "owner": repo.get("owner", {}).get("login"),
                        "html_url": repo.get("html_url"),
                        "installation_id": None,
                    }
                    if entry["private"]:
                        private_matches.append(entry)
                    else:
                        public_matches.append(entry)
        except Exception as e:
            logger.error(f"Failed to search repos on GitHub: {e}")

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
        if "feature_ids" in updates:
            updates["requested_feature_ids"] = updates.pop("feature_ids")
        if "max_builds" in updates:
            updates["max_builds_to_ingest"] = updates.pop("max_builds")

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
            feature_ids=[
                str(fid) for fid in getattr(repo_doc, "requested_feature_ids", [])
            ],
            max_builds=getattr(repo_doc, "max_builds_to_ingest", None),
        )

        return {"status": "queued"}

    def trigger_reprocess(self, repo_id: str):
        """
        Trigger re-extraction of features for all existing builds.

        Unlike trigger_sync (which fetches new workflow runs from GitHub),
        this method reprocesses existing builds to re-extract features.
        Useful when feature extractors have been updated.
        """
        from app.tasks.processing import reprocess_repo_builds

        repo_doc = self.repo_repo.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Queue the reprocess task
        reprocess_repo_builds.delay(repo_id)

        return {"status": "queued", "message": "Re-extraction of features queued"}
