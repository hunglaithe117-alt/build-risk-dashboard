import logging
from typing import List, Optional
from app.entities.enums import ModelImportStatus

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
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.github.github_client import (
    get_user_github_client,
)
from app.tasks.model_ingestion import import_repo


logger = logging.getLogger(__name__)


def _serialize_repo(repo_doc) -> RepoResponse:
    return RepoResponse.model_validate(repo_doc)


def _serialize_repo_detail(repo_doc) -> RepoDetailResponse:
    return RepoDetailResponse.model_validate(repo_doc)


class RepositoryService:
    def __init__(self, db: Database):
        self.db = db
        self.repo_config = ModelRepoConfigRepository(db)
        self.raw_repo = RawRepositoryRepository(db)

    def bulk_import_repositories(
        self, user_id: str, payloads: List[RepoImportRequest]
    ) -> List[RepoResponse]:
        """
        Import repositories by:
        1. Verify repo exists on GitHub (synchronous)
        2. Create/update RawRepository
        3. Create/update ModelRepoConfig with raw_repo_id
        4. Queue async import task
        """
        from app.services.github.github_client import get_app_github_client

        results = []

        for payload in payloads:
            target_user_id = user_id
            installation_id = payload.installation_id

            try:
                with get_app_github_client(self.db, installation_id) as gh:
                    repo_data = gh.get_repository(payload.full_name)

                if not repo_data:
                    logger.warning(
                        f"Repository {payload.full_name} not found on GitHub"
                    )
                    continue

                raw_repo = self.raw_repo.upsert_by_full_name(
                    full_name=payload.full_name,
                    github_repo_id=repo_data.get("id"),
                    default_branch=repo_data.get("default_branch", "main"),
                    is_private=bool(repo_data.get("private")),
                    main_lang=repo_data.get("language"),
                    github_metadata=repo_data,
                )

                repo_doc = self.repo_config.upsert_repository(
                    user_id=target_user_id,
                    full_name=payload.full_name,
                    data={
                        "provider": "github",
                        "raw_repo_id": raw_repo.id,  # Link to RawRepository
                        "installation_id": installation_id,
                        "test_frameworks": payload.test_frameworks,
                        "source_languages": payload.source_languages,
                        "ci_provider": payload.ci_provider,
                        "import_status": ModelImportStatus.QUEUED.value,
                        "max_builds_to_ingest": payload.max_builds,
                        "since_days": payload.since_days,
                        "only_with_logs": payload.only_with_logs,
                    },
                )

                import_repo.delay(
                    user_id=target_user_id,
                    full_name=payload.full_name,
                    installation_id=installation_id,
                    ci_provider=payload.ci_provider.value,
                    max_builds=payload.max_builds,
                    since_days=payload.since_days,
                    only_with_logs=payload.only_with_logs,
                )

                results.append(repo_doc)

            except Exception as e:
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

        repos, total = self.repo_config.list_by_user(
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
        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
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
        repo_doc = self.repo_config.get_repository(repo_id)
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
            updated = self.repo_config.update_repository(repo_id, updates)
            if not updated:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
                )

        return _serialize_repo_detail(updated)

    def trigger_sync(self, repo_id: str, user_id: str):
        """Trigger a full sync for a specific repository."""
        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Update status to queued/importing
        self.repo_config.update_repository(
            repo_id, {"import_status": ModelImportStatus.QUEUED.value}
        )

        # Trigger import task
        import_repo.delay(
            user_id=user_id,
            full_name=repo_doc.full_name,
            installation_id=repo_doc.installation_id,
            test_frameworks=repo_doc.test_frameworks,
            source_languages=repo_doc.source_languages,
            ci_provider=(
                repo_doc.ci_provider.value
                if hasattr(repo_doc.ci_provider, "value")
                else repo_doc.ci_provider
            ),
            max_builds=getattr(repo_doc, "max_builds_to_ingest", None),
            since_days=getattr(repo_doc, "since_days", None),
            only_with_logs=getattr(repo_doc, "only_with_logs", False),
        )

        return {"status": "queued"}

    def trigger_reprocess(self, repo_id: str):
        """
        Trigger re-extraction of features for all existing builds.

        Unlike trigger_sync (which fetches new workflow runs from GitHub),
        this method reprocesses existing builds to re-extract features.
        Useful when feature extractors have been updated.
        """
        from app.tasks.model_processing import reprocess_repo_builds

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Queue the reprocess task
        reprocess_repo_builds.delay(repo_id)

        return {"status": "queued", "message": "Re-extraction of features queued"}

    def detect_languages(self, full_name: str, current_user: dict) -> dict:
        """
        Detect repository languages via GitHub API.
        Returns top 5 languages (lowercase).
        """
        from app.services.github.github_client import (
            get_app_github_client,
            get_user_github_client,
        )

        user_id = str(current_user["_id"])

        # Check if repo is already imported with installation
        installation_id = None
        imported = self.repo_config.find_by_full_name(full_name)
        if imported and imported.installation_id:
            installation_id = imported.installation_id

        # Prefer installation if available, else fallback to user token
        if installation_id:
            client_ctx = get_app_github_client(self.db, installation_id)
        else:
            client_ctx = get_user_github_client(self.db, user_id)

        languages: list[str] = []
        try:
            with client_ctx as gh:
                stats = gh.list_languages(full_name) or {}
                languages = [
                    lang.lower()
                    for lang, _ in sorted(
                        stats.items(), key=lambda kv: kv[1], reverse=True
                    )[:5]
                ]
        except Exception as e:
            logger.warning("Failed to detect languages for %s: %s", full_name, e)

        return {"languages": languages}

    def list_test_frameworks(self) -> dict:
        """
        List supported test frameworks for log parsing.

        Returns:
            - frameworks: List of all supported framework names
            - by_language: Frameworks grouped by language
            - languages: List of languages with test framework support
        """
        from app.pipeline.feature_dag.log_parsers import LogParserRegistry

        registry = LogParserRegistry()

        return {
            "frameworks": registry.get_supported_frameworks(),
            "by_language": registry.get_frameworks_by_language(),
            "languages": registry.get_languages(),
        }

    def reprocess_build(self, repo_id: str, build_id: str, current_user: dict) -> dict:
        """
        Reprocess a build using the DAG-based feature pipeline.

        Useful for:
        - Retrying failed builds
        - Re-extracting features after pipeline updates
        """
        from app.tasks.model_processing import (
            reprocess_build as reprocess_build_task,
        )
        from app.entities.enums import ExtractionStatus
        from app.repositories.model_training_build import ModelTrainingBuildRepository
        from app.services.build_service import BuildService

        build_service = BuildService(self.db)
        build = build_service.get_build_detail(build_id)
        if not build:
            raise HTTPException(status_code=404, detail="Build not found")

        # Reset extraction status to pending before reprocessing
        build_repo = ModelTrainingBuildRepository(self.db)
        build_repo.update_one(
            build_id,
            {
                "extraction_status": ExtractionStatus.PENDING.value,
                "error_message": None,
            },
        )

        # Trigger async reprocessing
        reprocess_build_task.delay(build_id)

        return {
            "status": "queued",
            "build_id": build_id,
            "message": "Build reprocessing has been queued",
        }
