"""
Build Service - Query RawBuildRun as primary source with ModelTrainingBuild enrichment.

Flow:
1. Query raw_build_runs (available immediately after ingestion)
2. Left join with model_training_builds (optional - after processing)
3. Return merged data
"""

from typing import Any, Dict, List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.dtos.build import BuildDetail, BuildListResponse, BuildSummary
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository


class BuildService:
    """Service for querying builds with RawBuildRun as primary source."""

    def __init__(self, db: Database):
        self.db = db
        self.model_repo_config_repo = ModelRepoConfigRepository(db)
        self.model_training_build_repo = ModelTrainingBuildRepository(db)
        self.raw_build_run_repo = RawBuildRunRepository(db)
        self.raw_repo_repo = RawRepositoryRepository(db)

    def get_builds_by_repo(
        self,
        repo_id: str,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        extraction_status: Optional[str] = None,
    ) -> BuildListResponse:
        """
        Get builds for a repository.

        Shows only builds that have been processed for feature extraction
        (i.e., have a corresponding ModelTrainingBuild record).

        Args:
            repo_id: ModelRepoConfig._id or raw_repo_id
            skip: Pagination offset
            limit: Page size
            q: Search query (build number, commit sha)
            extraction_status: Filter by extraction status (pending/completed/failed/partial)
        """
        # Get model_repo_config to find the config ID
        try:
            config_oid = ObjectId(repo_id)
        except Exception:
            return BuildListResponse(items=[], total=0, page=1, size=limit)

        config = self.model_repo_config_repo.find_by_id(repo_id)
        if not config:
            return BuildListResponse(items=[], total=0, page=1, size=limit)

        # Query model_training_builds as primary source
        query: Dict[str, Any] = {"model_repo_config_id": config_oid}

        # Apply extraction_status filter
        if extraction_status:
            query["extraction_status"] = extraction_status

        # Apply search filter
        if q:
            or_conditions = []
            if q.isdigit():
                or_conditions.append({"build_number": int(q)})
            or_conditions.append({"head_sha": {"$regex": q, "$options": "i"}})
            if or_conditions:
                query["$or"] = or_conditions

        # Get total and paginated training builds
        total = self.db.model_training_builds.count_documents(query)
        training_cursor = (
            self.db.model_training_builds.find(query)
            .sort("build_created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        training_builds = list(training_cursor)

        if not training_builds:
            return BuildListResponse(items=[], total=total, page=skip // limit + 1, size=limit)

        # Get corresponding RawBuildRuns for additional data
        raw_ids = [t["raw_build_run_id"] for t in training_builds]
        raw_cursor = self.db.raw_build_runs.find({"_id": {"$in": raw_ids}})
        raw_map = {doc["_id"]: doc for doc in raw_cursor}

        # Build response items
        items = []
        for training in training_builds:
            raw = raw_map.get(training["raw_build_run_id"], {})

            items.append(
                BuildSummary(
                    _id=str(training["raw_build_run_id"]),
                    build_number=training.get("build_number") or raw.get("build_number"),
                    build_id=raw.get("build_id", ""),
                    conclusion=raw.get("conclusion", "unknown"),
                    commit_sha=training.get("head_sha") or raw.get("commit_sha", ""),
                    branch=raw.get("branch", ""),
                    created_at=training.get("build_created_at") or raw.get("created_at"),
                    completed_at=raw.get("completed_at"),
                    duration_seconds=raw.get("duration_seconds"),
                    web_url=raw.get("web_url"),
                    logs_available=raw.get("logs_available"),
                    logs_expired=raw.get("logs_expired", False),
                    # Training data - always available since we query from training builds
                    has_training_data=True,
                    training_build_id=str(training["_id"]),
                    extraction_status=training.get("extraction_status"),
                    feature_count=training.get("feature_count", 0),
                    extraction_error=training.get("extraction_error"),
                    missing_resources=training.get("missing_resources", []),
                )
            )

        return BuildListResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
        )

    def get_build_detail(self, build_id: str) -> Optional[BuildDetail]:
        """
        Get detailed build info by RawBuildRun._id.

        Args:
            build_id: RawBuildRun._id (MongoDB ObjectId string)
        """
        try:
            oid = ObjectId(build_id)
        except Exception:
            return None

        raw = self.raw_build_run_repo.find_by_id(oid)
        if not raw:
            return None

        # Get training data if exists
        training = self.model_training_build_repo.find_by_workflow_run(raw.raw_repo_id, oid)
        training_dict = training.model_dump() if training else None

        return BuildDetail(
            _id=str(raw.id),
            build_number=raw.build_number,
            build_id=raw.build_id or "",
            conclusion=raw.conclusion or "unknown",
            commit_sha=raw.commit_sha or "",
            branch=raw.branch or "",
            commit_message=raw.commit_message,
            commit_author=raw.commit_author,
            created_at=raw.created_at,
            started_at=raw.started_at,
            completed_at=raw.completed_at,
            duration_seconds=raw.duration_seconds,
            web_url=raw.web_url,
            provider=raw.provider or "github_actions",
            logs_available=raw.logs_available,
            logs_expired=raw.logs_expired or False,
            # Training enrichment
            has_training_data=training_dict is not None,
            training_build_id=str(training.id) if training else None,
            extraction_status=training_dict.get("extraction_status") if training_dict else None,
            feature_count=training_dict.get("feature_count", 0) if training_dict else 0,
            extraction_error=training_dict.get("extraction_error") if training_dict else None,
            features=training_dict.get("features", {}) if training_dict else {},
        )

    def get_recent_builds(self, limit: int = 10, current_user: dict = None) -> List[BuildSummary]:
        """Get most recent builds across repos accessible to user."""
        user_role = current_user.get("role", "user") if current_user else "admin"
        accessible_repos = current_user.get("github_accessible_repos", []) if current_user else []

        # Build query filter based on RBAC
        # Admin and guest see all, user sees filtered by accessible repos
        query = {}
        if user_role not in ("admin", "guest") and accessible_repos:
            # Get raw_repo_ids for accessible repos
            repo_filter = {
                "full_name": {"$in": accessible_repos},
                "is_deleted": {"$ne": True},
            }
            repos = self.db.repositories.find(repo_filter, {"raw_repo_id": 1})
            raw_repo_ids = [r["raw_repo_id"] for r in repos if r.get("raw_repo_id")]

            if not raw_repo_ids:
                return []
            query["raw_repo_id"] = {"$in": raw_repo_ids}

        raw_cursor = self.db.raw_build_runs.find(query).sort("created_at", -1).limit(limit)
        raw_builds = list(raw_cursor)

        if not raw_builds:
            return []

        # Get training data
        raw_ids = [b["_id"] for b in raw_builds]
        training_cursor = self.db.model_training_builds.find({"raw_build_run_id": {"$in": raw_ids}})
        training_map = {doc["raw_build_run_id"]: doc for doc in training_cursor}

        items = []
        for raw in raw_builds:
            training = training_map.get(raw["_id"])
            items.append(
                BuildSummary(
                    _id=str(raw["_id"]),
                    build_number=raw.get("build_number"),
                    build_id=raw.get("build_id", ""),
                    conclusion=raw.get("conclusion", "unknown"),
                    commit_sha=raw.get("commit_sha", ""),
                    branch=raw.get("branch", ""),
                    created_at=raw.get("created_at"),
                    completed_at=raw.get("completed_at"),
                    duration_seconds=raw.get("duration_seconds"),
                    web_url=raw.get("web_url"),
                    logs_available=raw.get("logs_available"),
                    logs_expired=raw.get("logs_expired", False),
                    has_training_data=training is not None,
                    training_build_id=str(training["_id"]) if training else None,
                    extraction_status=(training.get("extraction_status") if training else None),
                    feature_count=training.get("feature_count", 0) if training else 0,
                    extraction_error=(training.get("extraction_error") if training else None),
                    missing_resources=(training.get("missing_resources", []) if training else []),
                )
            )
        return items
