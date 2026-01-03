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
)
from app.entities.enums import ExtractionStatus
from app.entities.feature_audit_log import AuditLogCategory
from app.entities.model_repo_config import ModelImportStatus
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.services.github.github_client import (
    get_user_github_client,
)
from app.tasks.model_ingestion import start_model_processing
from app.tasks.model_processing import start_processing_phase

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

            is_org_owned = is_org_repo(payload.full_name)
            if is_org_owned:
                client_ctx = get_app_github_client()
            else:
                client_ctx = get_user_github_client(self.db, user_id)

            with client_ctx as gh:
                repo_data = gh.get_repository(payload.full_name)

            if not repo_data:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=(
                        f"Repository '{payload.full_name}' not found on "
                        "GitHub or you don't have access."
                    ),
                )

            is_private = bool(repo_data.get("private"))
            if is_private and not is_org_owned:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Repository '{payload.full_name}' is private "
                        "and not owned by the organization."
                    ),
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

            # Check if repo already exists (with hard delete, this is simple)
            existing_config = self.repo_config.find_by_full_name(payload.full_name)

            if existing_config:
                # Already imported - reject
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Repository '{payload.full_name}' is already "
                        "imported. Delete it first to re-import."
                    ),
                )

            # Create new config
            repo_doc = self.repo_config.insert_one(
                ModelRepoConfig(
                    _id=None,
                    user_id=ObjectId(target_user_id),
                    full_name=payload.full_name,
                    raw_repo_id=raw_repo.id,
                    ci_provider=payload.ci_provider,
                    status=ModelImportStatus.QUEUED,
                    max_builds_to_ingest=payload.max_builds,
                    since_days=payload.since_days,
                    only_with_logs=payload.only_with_logs or False,
                    feature_configs=payload.feature_configs or {},
                )
            )

            # Publish status immediately for real-time UI update
            from app.tasks.shared.events import publish_repo_status

            publish_repo_status(
                str(repo_doc.id),
                "queued",
                f"Repository {payload.full_name} queued for import",
            )

            start_model_processing.delay(
                repo_config_id=str(repo_doc.id),
                ci_provider=payload.ci_provider.value,
                max_builds=payload.max_builds,
                since_days=payload.since_days,
                only_with_logs=payload.only_with_logs,
            )

            results.append(repo_doc)

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
                            "github_repo_id": repo.get("id"),
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
                                "github_repo_id": repo.get("id"),
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
                            "github_repo_id": repo.get("id"),
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

    def trigger_sync(self, repo_id: str, user_id: str):
        """
        Trigger a sync to fetch new builds for a repository (ingestion only).

        Uses sync_until_existing mode: fetches from newest builds until
        hitting existing builds, then stops.

        Processing is NOT started automatically - user must manually
        click "Start Processing" to process the new builds.
        """
        from app.repositories.model_training_build import ModelTrainingBuildRepository
        from app.tasks.model_ingestion import ingest_model_builds

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Check if already importing
        if repo_doc.status in (ModelImportStatus.INGESTING, ModelImportStatus.PROCESSING):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Repository is already being imported. Please wait for completion.",
            )

        # Check for pending/failed training builds (temporal dependency check)
        training_build_repo = ModelTrainingBuildRepository(self.db)
        pending_count = training_build_repo.count_by_config(
            ObjectId(repo_id), ExtractionStatus.PENDING
        )
        failed_count = training_build_repo.count_by_config(
            ObjectId(repo_id), ExtractionStatus.FAILED
        )

        if pending_count > 0 or failed_count > 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot sync: {pending_count} pending and {failed_count} failed builds. "
                    "Process or retry these builds first to maintain temporal feature integrity."
                ),
            )

        # Update status to queued/ingesting
        self.repo_config.update_repository(repo_id, {"status": ModelImportStatus.QUEUED.value})

        # Trigger INGESTION only (not processing) with sync_until_existing mode
        ingest_model_builds.delay(
            repo_config_id=repo_id,
            ci_provider=(
                repo_doc.ci_provider.value
                if hasattr(repo_doc.ci_provider, "value")
                else repo_doc.ci_provider
            ),
            sync_until_existing=True,
            only_with_logs=getattr(repo_doc, "only_with_logs", False),
        )

        return {"status": "queued", "phase": "ingestion"}

    def trigger_reprocess_failed(self, repo_id: str):
        """
        Trigger unified retry for all failed builds (extraction + prediction).

        This handles both:
        - Extraction FAILED builds → full pipeline (extract + predict)
        - Extraction OK + Prediction FAILED → predict only (skip extraction)

        Unlike trigger_sync (which fetches new workflow runs from GitHub),
        this method only retries failed builds.
        """
        from app.tasks.model_processing import retry_failed_builds

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Queue the unified retry task
        retry_failed_builds.delay(repo_id)

        return {"status": "queued", "message": "Retry of failed builds queued"}

    def trigger_reingest_failed(self, repo_id: str):
        """
        Trigger re-ingestion of only FAILED import builds.

        This method retries builds that failed during the ingestion phase
        (fetch, clone, worktree creation, log download).
        """
        from app.tasks.model_ingestion import reingest_failed_builds

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Queue the reingest task
        reingest_failed_builds.delay(repo_id)

        return {"status": "queued", "message": "Re-ingestion of failed builds queued"}

    def delete_repository(self, repo_id: str) -> None:
        """
        Hard delete a repository configuration and all associated builds atomically.

        Cascade deletes:
        - FeatureAuditLog (audit logs)
        - ModelImportBuild (import tracking)
        - ModelTrainingBuild (extracted features)
        - ModelRepoConfig (the config itself)

        Uses MongoDB transaction for atomicity.
        """
        from app.database.mongo import get_transaction
        from app.repositories.feature_audit_log import FeatureAuditLogRepository
        from app.repositories.feature_vector import FeatureVectorRepository
        from app.repositories.model_import_build import ModelImportBuildRepository
        from app.repositories.model_training_build import ModelTrainingBuildRepository

        repo_doc = self.repo_config.find_by_id(repo_id)
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        audit_log_repo = FeatureAuditLogRepository(self.db)
        import_build_repo = ModelImportBuildRepository(self.db)
        training_build_repo = ModelTrainingBuildRepository(self.db)
        feature_vector_repo = FeatureVectorRepository(self.db)
        repo_oid = ObjectId(repo_id)
        raw_repo_oid = repo_doc.raw_repo_id

        # Collect feature_vector_ids from training builds BEFORE deleting them
        training_builds = list(
            training_build_repo.collection.find(
                {"model_repo_config_id": repo_oid},
                {"feature_vector_id": 1},
            )
        )
        feature_vector_ids = [
            b["feature_vector_id"] for b in training_builds if b.get("feature_vector_id")
        ]

        # Use transaction for atomic cascade deletion
        with get_transaction() as session:
            # 1. Delete FeatureAuditLog documents
            audit_deleted = audit_log_repo.delete_by_raw_repo_id(
                raw_repo_oid, AuditLogCategory.MODEL_TRAINING, session=session
            )
            logger.info(f"Deleted {audit_deleted} FeatureAuditLog for raw_repo {raw_repo_oid}")

            # 2. Delete FeatureVector documents (by feature_vector_ids)
            if feature_vector_ids:
                fv_deleted = feature_vector_repo.delete_by_ids(feature_vector_ids, session=session)
                logger.info(f"Deleted {fv_deleted} FeatureVector for repo config {repo_id}")

            # 3. Delete ModelImportBuild documents
            import_deleted = import_build_repo.delete_by_repo_config(repo_oid, session=session)
            logger.info(f"Deleted {import_deleted} ModelImportBuild for repo config {repo_id}")

            # 4. Delete ModelTrainingBuild documents
            training_deleted = training_build_repo.delete_by_repo_config(repo_oid, session=session)
            logger.info(f"Deleted {training_deleted} ModelTrainingBuild for repo config {repo_id}")

            # 5. Hard delete the config itself
            self.repo_config.hard_delete(repo_oid, session=session)
            logger.info(f"Hard deleted repository config {repo_id}")

    def get_import_progress(self, repo_id: str) -> dict:
        """
        Get detailed import progress breakdown.

        Returns counts by ModelImportBuild status, including:
        - Total stats (all builds)
        - Current batch stats (builds after checkpoint)
        - Checkpoint info (timestamp and accepted failures)
        """
        from app.repositories.model_import_build import ModelImportBuildRepository
        from app.repositories.model_training_build import ModelTrainingBuildRepository

        repo_doc = self.repo_config.find_by_id(repo_id)
        if not repo_doc:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Repository not found")

        import_build_repo = ModelImportBuildRepository(self.db)
        training_build_repo = ModelTrainingBuildRepository(self.db)

        # Get counts by import status (total)
        import_status_counts = import_build_repo.count_by_status(repo_id)

        # Get extraction status counts from training builds
        extraction_pipeline = [
            {"$match": {"model_repo_config_id": ObjectId(repo_id)}},
            {"$group": {"_id": "$extraction_status", "count": {"$sum": 1}}},
        ]
        extraction_results = list(training_build_repo.collection.aggregate(extraction_pipeline))
        extraction_counts = {r["_id"]: r["count"] for r in extraction_results if r["_id"]}

        # Get prediction stats from training builds
        prediction_pipeline = [
            {"$match": {"model_repo_config_id": ObjectId(repo_id)}},
            {
                "$group": {
                    "_id": None,
                    "with_prediction": {
                        "$sum": {"$cond": [{"$ne": ["$predicted_label", None]}, 1, 0]}
                    },
                    "prediction_failed": {
                        "$sum": {"$cond": [{"$ne": ["$prediction_error", None]}, 1, 0]}
                    },
                    "total_processed": {
                        "$sum": {
                            "$cond": [
                                {"$in": ["$extraction_status", ["completed", "partial"]]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]
        prediction_results = list(training_build_repo.collection.aggregate(prediction_pipeline))
        prediction_stats = prediction_results[0] if prediction_results else {}

        with_prediction = prediction_stats.get("with_prediction", 0)
        prediction_failed = prediction_stats.get("prediction_failed", 0)
        total_processed = prediction_stats.get("total_processed", 0)
        pending_prediction = max(0, total_processed - with_prediction - prediction_failed)

        # Get per-resource status summary (git_history, git_worktree, build_logs)
        resource_status_summary = import_build_repo.get_resource_status_summary(repo_id)

        # Checkpoint: use ObjectId for reliable ordering
        last_checkpoint_id = repo_doc.last_processed_import_build_id

        # Look up the build_number of the last processed build
        current_processing_build_number = None
        if last_checkpoint_id:
            last_import_build = import_build_repo.find_by_id(last_checkpoint_id)
            if last_import_build and last_import_build.raw_build_run_id:
                from app.repositories.raw_build_run import RawBuildRunRepository

                raw_build_repo = RawBuildRunRepository(self.db)
                raw_build = raw_build_repo.find_by_id(last_import_build.raw_build_run_id)
                if raw_build:
                    current_processing_build_number = raw_build.build_number

        # Count missing resource builds that can be retried (after checkpoint)
        missing_resource_retryable = import_build_repo.count_missing_resource_after_checkpoint(
            repo_id, last_checkpoint_id
        )

        return {
            "repo_id": repo_id,
            "status": repo_doc.status.value
            if hasattr(repo_doc.status, "value")
            else repo_doc.status,
            # === CHECKPOINT INFO (simplified) ===
            "checkpoint": {
                "has_checkpoint": last_checkpoint_id is not None,
                "last_processed_import_build_id": (
                    str(last_checkpoint_id) if last_checkpoint_id else None
                ),
                "current_processing_build_number": current_processing_build_number,
            },
            # Import phase (ModelImportBuild) - TOTAL
            "import_builds": {
                "pending": import_status_counts.get("pending", 0),
                "fetched": import_status_counts.get("fetched", 0),
                "ingesting": import_status_counts.get("ingesting", 0),
                "ingested": import_status_counts.get("ingested", 0),
                "missing_resource": import_status_counts.get("missing_resource", 0),
                "missing_resource_retryable": missing_resource_retryable,
                "total": sum(import_status_counts.values()),
            },
            # Per-resource status breakdown
            "resource_status": resource_status_summary,
            # Processing phase (ModelTrainingBuild)
            "training_builds": {
                "pending": extraction_counts.get("pending", 0),
                "completed": extraction_counts.get("completed", 0),
                "partial": extraction_counts.get("partial", 0),
                "failed": extraction_counts.get("failed", 0),
                "total": sum(extraction_counts.values()),
                # Prediction stats
                "with_prediction": with_prediction,
                "pending_prediction": pending_prediction,
                "prediction_failed": prediction_failed,
            },
            # Summary from repo config
            "summary": {
                "builds_fetched": repo_doc.builds_fetched,
                "builds_completed": repo_doc.builds_completed,
                "builds_missing_resource": repo_doc.builds_missing_resource,
                "builds_processing_failed": repo_doc.builds_processing_failed,
            },
        }

    def get_failed_import_builds(self, repo_id: str, limit: int = 50) -> dict:
        """
        Get failed import builds with error details for UI display.

        Returns list of failed builds with their errors (ingestion_error + resource_errors).
        """
        from app.repositories.model_import_build import ModelImportBuildRepository

        repo_doc = self.repo_config.find_by_id(repo_id)
        if not repo_doc:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Repository not found")

        import_build_repo = ModelImportBuildRepository(self.db)
        missing_resource_builds = import_build_repo.get_missing_resource_builds_with_errors(
            repo_id, limit
        )

        return {
            "repo_id": repo_id,
            "total": len(missing_resource_builds),
            "missing_resource_builds": missing_resource_builds,
        }

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
        cursor = build_repo.get_for_export(ObjectId(repo_id), limit=10)

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

    def start_processing(self, repo_id: str) -> dict:
        """
        Trigger Phase 2: Start processing (feature extraction + prediction).

        Allowed when:
        - INGESTED: First processing after ingestion
        - PROCESSED: Re-processing after new sync

        Uses checkpoint to only process new builds since last processing.
        FAILED status is only set by ModelPipelineTask on unhandled exceptions.

        Raises:
            HTTPException: If repository not found or status is invalid
        """

        repo_doc = self.repo_config.find_by_id(ObjectId(repo_id))
        if not repo_doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found"
            )

        # Validate status
        current_status = repo_doc.status
        if hasattr(current_status, "value"):
            current_status = current_status.value

        valid_statuses = [
            ModelImportStatus.INGESTED.value,
            ModelImportStatus.PROCESSED.value,
        ]

        if current_status not in valid_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Cannot start processing: status is '{current_status}'. "
                    f"Expected: ingested or processed."
                ),
            )

        # Queue the processing task
        start_processing_phase.delay(repo_config_id=repo_id)

        return {
            "status": "queued",
            "message": "Processing phase started. Feature extraction will begin shortly.",
        }
