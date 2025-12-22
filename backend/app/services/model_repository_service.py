import logging
from typing import List, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app.config import settings
from app.dtos import (
    RepoDetailResponse,
    RepoImportRequest,
    RepoListResponse,
    RepoResponse,
    RepoSearchResponse,
    RepoSuggestionListResponse,
    RepoUpdateRequest,
)
from app.entities.enums import ModelImportStatus
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.github.github_client import (
    get_user_github_client,
)
from app.tasks.model_processing import start_model_processing

logger = logging.getLogger(__name__)


def is_org_repo(full_name: str) -> bool:
    """
    Check if a repository belongs to the configured organization.

    Args:
        full_name: Repository full name in format "owner/repo"

    Returns:
        True if owner matches GITHUB_ORGANIZATION, False otherwise
    """
    from app.config import settings

    if not settings.GITHUB_ORGANIZATION:
        return False

    parts = full_name.split("/")
    if len(parts) != 2:
        return False

    owner = parts[0].lower()
    configured_org = settings.GITHUB_ORGANIZATION.lower()
    return owner == configured_org


def _serialize_repo(repo_doc) -> RepoResponse:
    return RepoResponse.model_validate(repo_doc)


def _serialize_repo_detail(repo_doc, raw_repo_doc=None) -> RepoDetailResponse:
    # Convert ModelRepoConfig to dict
    data = repo_doc.model_dump(by_alias=True)

    # Merge RawRepository data if available
    if raw_repo_doc:
        data.update(
            {
                "default_branch": raw_repo_doc.default_branch,
                "is_private": raw_repo_doc.is_private,
                "main_lang": raw_repo_doc.main_lang,
                "github_repo_id": raw_repo_doc.github_repo_id,
                "metadata": raw_repo_doc.github_metadata,
            }
        )

    return RepoDetailResponse.model_validate(data)


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
        4. Queue async import task (if not already importing)

        Returns list of successfully imported repos.
        Raises HTTPException for user input errors (e.g., repo already exists).
        """
        from app.services.github.github_client import get_app_github_client

        results = []

        for payload in payloads:
            target_user_id = user_id

            try:
                from app.config import settings

                is_org_owned = is_org_repo(payload.full_name)
                if is_org_owned:
                    client_ctx = get_app_github_client(self.db, settings.GITHUB_INSTALLATION_ID)
                else:
                    client_ctx = get_user_github_client(self.db, user_id)

                with client_ctx as gh:
                    repo_data = gh.get_repository(payload.full_name)

                if not repo_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Repository '{payload.full_name}' not found on GitHub or you don't have access.",
                    )

                is_private = bool(repo_data.get("private"))
                if is_private and not is_org_owned:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Repository '{payload.full_name}' is private and not owned by the organization.",
                    )

                raw_repo = self.raw_repo.upsert_by_full_name(
                    full_name=payload.full_name,
                    github_repo_id=repo_data.get("id"),
                    default_branch=repo_data.get("default_branch", "main"),
                    is_private=is_private,
                    main_lang=repo_data.get("language"),
                    github_metadata=repo_data,
                )

                from app.entities.model_repo_config import ModelRepoConfig

                # Find by full_name INCLUDING deleted records to avoid duplicates
                existing_config = self.repo_config.find_by_full_name_include_deleted(
                    payload.full_name
                )

                if existing_config:
                    # Check if it's an active (non-deleted) config
                    if not existing_config.is_deleted:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Repository '{payload.full_name}' is already imported. Please delete it first to re-import.",
                        )

                    # Re-activate deleted config with new settings
                    repo_doc = self.repo_config.update_one(
                        existing_config.id,
                        {
                            "user_id": ObjectId(target_user_id),
                            "raw_repo_id": raw_repo.id,  # Update in case raw_repo changed
                            "test_frameworks": payload.test_frameworks or [],
                            "source_languages": payload.source_languages or [],
                            "ci_provider": payload.ci_provider,
                            "import_status": ModelImportStatus.QUEUED,
                            "max_builds_to_ingest": payload.max_builds,
                            "since_days": payload.since_days,
                            "only_with_logs": payload.only_with_logs or False,
                            "is_deleted": False,  # Re-activate
                            "deleted_at": None,
                            "import_error": None,
                            "import_version": existing_config.import_version + 1,
                            # Reset stats for fresh re-import
                            "total_builds_imported": 0,
                            "total_builds_processed": 0,
                            "total_builds_failed": 0,
                            "feature_extractors": [],
                            "last_synced_at": None,
                            "last_sync_status": None,
                            "last_sync_error": None,
                            "import_started_at": None,
                            "import_completed_at": None,
                        },
                    )
                else:
                    # No existing config - create new
                    repo_doc = self.repo_config.insert_one(
                        ModelRepoConfig(
                            _id=None,
                            user_id=ObjectId(target_user_id),
                            full_name=payload.full_name,
                            raw_repo_id=raw_repo.id,
                            test_frameworks=payload.test_frameworks or [],
                            source_languages=payload.source_languages or [],
                            ci_provider=payload.ci_provider,
                            import_status=ModelImportStatus.QUEUED,
                            max_builds_to_ingest=payload.max_builds,
                            since_days=payload.since_days,
                            only_with_logs=payload.only_with_logs or False,
                        )
                    )

                start_model_processing.delay(
                    repo_config_id=str(repo_doc.id),
                    ci_provider=payload.ci_provider.value,
                    max_builds=payload.max_builds,
                    since_days=payload.since_days,
                    only_with_logs=payload.only_with_logs,
                )

                results.append(repo_doc)

            except Exception as e:
                logger.error(f"Internal error importing {payload.full_name}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to import '{payload.full_name}'. Please try again later.",
                )

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
                            "html_url": repo.get("html_url"),
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to fetch user repos from GitHub: {e}")

        return RepoSuggestionListResponse(items=items[:limit])

    def list_repositories(
        self, current_user: dict, skip: int, limit: int, q: Optional[str] = None
    ) -> RepoListResponse:
        """List tracked repositories with RBAC access control."""
        user_id = ObjectId(current_user["_id"])
        user_role = current_user.get("role", "user")
        github_accessible_repos = current_user.get("github_accessible_repos", [])

        repos, total = self.repo_config.list_with_access_control(
            user_id=user_id,
            user_role=user_role,
            skip=skip,
            limit=limit,
            search_query=q,
            github_accessible_repos=github_accessible_repos,
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
        """Search for repositories directly against GitHub.

        Returns:
            - private_matches: Repos in the configured org (for "Your Repositories")
            - public_matches: Other public repos on GitHub (for "Public GitHub Repositories")
        """
        from app.config import settings

        org_matches: List[dict] = []  # Repos in org -> "Your Repositories"
        public_matches: List[dict] = []  # Other public repos

        if not q or len(q) < 1:
            return RepoSearchResponse(private_matches=[], public_matches=[])

        org = settings.GITHUB_ORGANIZATION

        try:
            with get_user_github_client(self.db, user_id) as gh:
                # 1. Search within organization (if configured)
                if org:
                    org_query = f"{q} org:{org}"
                    org_results = gh.search_repositories(org_query, per_page=20)
                    for repo in org_results:
                        owner = repo.get("owner", {}).get("login", "")
                        if owner.lower() != org.lower():
                            continue
                        org_matches.append(
                            {
                                "full_name": repo.get("full_name"),
                                "description": repo.get("description"),
                                "default_branch": repo.get("default_branch"),
                                "private": bool(repo.get("private")),
                                "owner": owner,
                                "html_url": repo.get("html_url"),
                            }
                        )

                # 2. Search public repos (exclude org repos to avoid duplicates)
                public_results = gh.search_repositories(q, per_page=10)
                org_lower = org.lower() if org else ""
                for repo in public_results:
                    owner = repo.get("owner", {}).get("login", "")
                    # Skip private repos and repos already in org_matches
                    if repo.get("private"):
                        continue
                    if org and owner.lower() == org_lower:
                        continue
                    public_matches.append(
                        {
                            "full_name": repo.get("full_name"),
                            "description": repo.get("description"),
                            "default_branch": repo.get("default_branch"),
                            "private": False,
                            "owner": owner,
                            "html_url": repo.get("html_url"),
                        }
                    )
        except Exception as e:
            logger.error(f"Failed to search repos on GitHub: {e}")

        return RepoSearchResponse(
            private_matches=org_matches,  # "Your Repositories (App Installed)"
            public_matches=public_matches,  # "Public GitHub Repositories"
        )

    def get_repository_detail(self, repo_id: str, current_user: dict) -> RepoDetailResponse:
        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Check RBAC access
        user_id = ObjectId(current_user["_id"])
        user_role = current_user.get("role", "user")
        github_accessible_repos = current_user.get("github_accessible_repos", [])

        if not self.repo_config.can_user_access(
            ObjectId(repo_id), user_id, user_role, github_accessible_repos
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to access this repository",
            )

        # Fetch raw repository data
        raw_repo_doc = self.raw_repo.find_by_id(repo_doc.raw_repo_id)

        return _serialize_repo_detail(repo_doc, raw_repo_doc)

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

        # Check if already importing
        if repo_doc.import_status == ModelImportStatus.IMPORTING:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository is already being imported. Please wait for completion.",
            )

        # Update status to queued/importing
        self.repo_config.update_repository(
            repo_id, {"import_status": ModelImportStatus.QUEUED.value}
        )

        # Trigger import task
        start_model_processing.delay(
            repo_config_id=repo_id,
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

    def delete_repository(self, repo_id: str) -> None:
        """
        Soft delete a repository configuration atomically.

        This allows re-importing the same repository later.
        Also deletes associated ModelTrainingBuild documents.
        """
        from app.database.mongo import get_transaction
        from app.repositories.model_training_build import ModelTrainingBuildRepository

        repo_doc = self.repo_config.find_by_id(repo_id)
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Check if already deleted
        if repo_doc.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository is already deleted",
            )

        build_repo = ModelTrainingBuildRepository(self.db)

        # Use transaction for atomic deletion
        with get_transaction() as session:
            # Delete associated ModelTrainingBuild documents
            deleted_count = build_repo.delete_by_repo_config(ObjectId(repo_id), session=session)
            logger.info(
                f"Deleted {deleted_count} ModelTrainingBuild documents for repo config {repo_id}"
            )

            # Soft delete the config
            self.repo_config.soft_delete(ObjectId(repo_id), session=session)
            logger.info(f"Soft deleted repository config {repo_id}")

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

        # Use GitHub App if configured, else fallback to user token
        if settings.GITHUB_INSTALLATION_ID:
            client_ctx = get_app_github_client()
        else:
            client_ctx = get_user_github_client(self.db, user_id)

        languages: list[str] = []
        try:
            with client_ctx as gh:
                stats = gh.list_languages(full_name) or {}
                languages = [
                    lang.lower()
                    for lang, _ in sorted(stats.items(), key=lambda kv: kv[1], reverse=True)[:5]
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
        from app.tasks.pipeline.feature_dag.log_parsers import LogParserRegistry

        registry = LogParserRegistry()

        return {
            "frameworks": registry.get_supported_frameworks(),
            "by_language": registry.get_frameworks_by_language(),
            "languages": registry.get_languages(),
        }

    def reprocess_build(self, repo_id: str, raw_build_run_id: str, current_user: dict) -> dict:
        """
        Reprocess a build using the DAG-based feature pipeline.

        Useful for:
        - Retrying failed builds
        - Re-extracting features after pipeline updates

        Args:
            repo_id: ModelRepoConfig._id (MongoDB ObjectId string)
            raw_build_run_id: RawBuildRun._id (MongoDB ObjectId string)
                              This is what the UI sends from Build History table
            current_user: Current authenticated user

        Note on ID types:
            - raw_build_run_id: The RawBuildRun._id shown in UI (from Build History)
            - model_training_build_id: The ModelTrainingBuild._id needed by the task
            - ci_run_id: CI provider's workflow ID (e.g., GitHub run ID like "20349163111")
        """
        from app.entities.enums import ExtractionStatus
        from app.repositories.model_training_build import ModelTrainingBuildRepository
        from app.services.model_build_service import BuildService
        from app.tasks.model_processing import (
            reprocess_build as reprocess_build_task,
        )

        # Validate raw build exists
        build_service = BuildService(self.db)
        build = build_service.get_build_detail(raw_build_run_id)
        if not build:
            raise HTTPException(status_code=404, detail="Build not found")

        # Find corresponding ModelTrainingBuild by raw_build_run_id
        build_repo = ModelTrainingBuildRepository(self.db)
        model_training_build = build_repo.find_one({"raw_build_run_id": ObjectId(raw_build_run_id)})

        if not model_training_build:
            raise HTTPException(
                status_code=404,
                detail="ModelTrainingBuild not found for this build. "
                "The build may not have been processed yet.",
            )

        model_training_build_id = str(model_training_build.id)

        # Reset extraction status to pending before reprocessing
        build_repo.update_one(
            model_training_build_id,
            {
                "extraction_status": ExtractionStatus.PENDING.value,
                "extraction_error": None,
            },
        )

        # Trigger async reprocessing with the correct ModelTrainingBuild._id
        reprocess_build_task.delay(model_training_build_id)

        return {
            "status": "queued",
            "raw_build_run_id": raw_build_run_id,
            "model_training_build_id": model_training_build_id,
            "message": "Build reprocessing has been queued",
        }

    # Export Methods
    def export_builds_stream(
        self,
        repo_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
        start_date=None,
        end_date=None,
        build_status: Optional[str] = None,
    ):
        """
        Stream export builds as CSV or JSON.

        For small datasets (< 1000 rows).
        """
        from app.repositories.model_training_build import ModelTrainingBuildRepository
        from app.utils.export_utils import (
            format_feature_row,
            stream_csv,
            stream_json,
        )

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        build_repo = ModelTrainingBuildRepository(self.db)

        # Get cursor for streaming
        cursor = build_repo.get_for_export(ObjectId(repo_id), start_date, end_date, build_status)

        # Get all feature keys for consistent CSV columns
        all_feature_keys = None
        if format == "csv" and not features:
            all_feature_keys = build_repo.get_all_feature_keys(
                ObjectId(repo_id), start_date, end_date, build_status
            )

        if format == "csv":
            return stream_csv(cursor, format_feature_row, features, all_feature_keys)
        else:
            return stream_json(cursor, format_feature_row, features)

    def get_export_preview(self, repo_id: str, current_user: dict) -> dict:
        """Get preview of exportable data with sample rows."""
        from app.repositories.model_training_build import ModelTrainingBuildRepository

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        build_repo = ModelTrainingBuildRepository(self.db)

        # Get sample builds
        cursor = build_repo.get_for_export(ObjectId(repo_id)).limit(10)

        sample_rows = []
        all_features = set()

        for doc in cursor:
            features = doc.get("features", {})
            sample_rows.append(features)
            all_features.update(features.keys())

        # Get total count
        total = build_repo.count_for_export(ObjectId(repo_id))

        return {
            "total_rows": total,
            "sample_rows": sample_rows,
            "available_features": sorted(all_features),
            "feature_count": len(all_features),
        }

    def create_export_job(
        self,
        repo_id: str,
        user_id: str,
        format: str = "csv",
        features: Optional[List[str]] = None,
        start_date=None,
        end_date=None,
        build_status: Optional[str] = None,
    ) -> dict:
        """
        Create background export job for large datasets.

        Returns job ID for tracking progress.
        """
        from app.entities.export_job import ExportFormat, ExportJob, ExportStatus
        from app.repositories.export_job import ExportJobRepository
        from app.repositories.model_training_build import ModelTrainingBuildRepository
        from app.tasks.export import process_export_job

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        build_repo = ModelTrainingBuildRepository(self.db)
        total = build_repo.count_for_export(ObjectId(repo_id), start_date, end_date, build_status)

        if total == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No builds available for export",
            )

        job_repo = ExportJobRepository(self.db)

        job = ExportJob(
            repo_id=ObjectId(repo_id),
            user_id=ObjectId(user_id),
            format=ExportFormat(format),
            status=ExportStatus.PENDING,
            features=features,
            start_date=start_date,
            end_date=end_date,
            build_status=build_status,
            total_rows=total,
        )

        job = job_repo.create(job)

        # Queue background task
        process_export_job.delay(str(job.id))

        return {
            "job_id": str(job.id),
            "status": "pending",
            "total_rows": total,
        }

    def get_export_job(self, job_id: str) -> dict:
        """Get export job status."""
        from app.repositories.export_job import ExportJobRepository

        job_repo = ExportJobRepository(self.db)
        job = job_repo.find_by_id(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found"
            )

        return {
            "id": str(job.id),
            "status": job.status,
            "format": job.format,
            "total_rows": job.total_rows,
            "processed_rows": job.processed_rows,
            "progress": job.processed_rows / job.total_rows * 100 if job.total_rows else 0,
            "file_path": job.file_path,
            "file_size": job.file_size,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        }

    def list_export_jobs(self, repo_id: str, limit: int = 10) -> list:
        """List export jobs for a repository."""
        from app.repositories.export_job import ExportJobRepository

        job_repo = ExportJobRepository(self.db)
        jobs = job_repo.list_by_repo(repo_id, limit)

        return [
            {
                "id": str(j.id),
                "status": j.status,
                "format": j.format,
                "total_rows": j.total_rows,
                "processed_rows": j.processed_rows,
                "file_size": j.file_size,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "completed_at": j.completed_at.isoformat() if j.completed_at else None,
            }
            for j in jobs
        ]

    def get_export_download_path(self, job_id: str, user_id: str) -> str:
        """Get file path for completed export job."""
        from app.repositories.export_job import ExportJobRepository

        job_repo = ExportJobRepository(self.db)
        job = job_repo.find_by_id(job_id)

        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Export job not found"
            )

        if str(job.user_id) != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to download this export",
            )

        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Export is not ready. Status: {job.status}",
            )

        if not job.file_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Export file not found",
            )

        return job.file_path
