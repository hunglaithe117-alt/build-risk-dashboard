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

from app.dtos.build import (
    BuildDetail,
    BuildListResponse,
    BuildSummary,
    ImportBuildListResponse,
    TrainingBuildListResponse,
)
from app.repositories.model_repo_config import ModelRepoConfigRepository
from app.repositories.model_training_build import ModelTrainingBuildRepository
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository


class ModelBuildService:
    """Service for querying model builds (ModelTrainingBuild) with RawBuildRun enrichment."""

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

        if extraction_status:
            # Query model_training_builds as primary source when filtering by status
            query: Dict[str, Any] = {"model_repo_config_id": config_oid}
            query["extraction_status"] = extraction_status

            if q:
                or_conditions = []
                if q.isdigit():
                    or_conditions.append({"build_number": int(q)})
                or_conditions.append({"head_sha": {"$regex": q, "$options": "i"}})
                if or_conditions:
                    query["$or"] = or_conditions

            total = self.db.model_training_builds.count_documents(query)
            training_cursor = (
                self.db.model_training_builds.find(query)
                .sort("build_created_at", -1)
                .skip(skip)
                .limit(limit)
            )
            training_builds = list(training_cursor)

            if not training_builds:
                return BuildListResponse(
                    items=[], total=total, page=skip // limit + 1, size=limit
                )

            raw_ids = [t["raw_build_run_id"] for t in training_builds]
            raw_cursor = self.db.raw_build_runs.find({"_id": {"$in": raw_ids}})
            raw_map = {doc["_id"]: doc for doc in raw_cursor}

            items = []
            for training in training_builds:
                raw = raw_map.get(training["raw_build_run_id"], {})
                items.append(
                    BuildSummary(
                        _id=str(training["raw_build_run_id"]),
                        build_number=training.get("build_number")
                        or raw.get("build_number"),
                        build_id=raw.get("build_id", ""),
                        conclusion=raw.get("conclusion", "unknown"),
                        commit_sha=training.get("head_sha")
                        or raw.get("commit_sha", ""),
                        branch=raw.get("branch", ""),
                        created_at=training.get("build_created_at")
                        or raw.get("created_at"),
                        completed_at=raw.get("completed_at"),
                        duration_seconds=raw.get("duration_seconds"),
                        web_url=raw.get("web_url"),
                        logs_available=raw.get("logs_available"),
                        logs_expired=raw.get("logs_expired", False),
                        has_training_data=True,
                        training_build_id=str(training["_id"]),
                        extraction_status=training.get("extraction_status"),
                        feature_count=training.get("feature_count", 0),
                        extraction_error=training.get("extraction_error"),
                        missing_resources=training.get("missing_resources", []),
                        prediction_status=training.get("prediction_status", "pending"),
                        prediction_error=training.get("prediction_error"),
                    )
                )

        else:
            # Query RawBuildRun as primary source (show all ingested builds)
            query = {"raw_repo_id": config.raw_repo_id}

            if q:
                or_conditions = []
                if q.isdigit():
                    or_conditions.append({"build_number": int(q)})
                or_conditions.append({"commit_sha": {"$regex": q, "$options": "i"}})
                if or_conditions:
                    query["$or"] = or_conditions

            total = self.db.raw_build_runs.count_documents(query)
            raw_cursor = (
                self.db.raw_build_runs.find(query)
                .sort("created_at", -1)
                .skip(skip)
                .limit(limit)
            )
            raw_builds = list(raw_cursor)

            if not raw_builds:
                return BuildListResponse(
                    items=[], total=total, page=skip // limit + 1, size=limit
                )

            # Left join with model_training_builds
            raw_ids = [b["_id"] for b in raw_builds]
            training_cursor = self.db.model_training_builds.find(
                {
                    "raw_build_run_id": {"$in": raw_ids},
                    "model_repo_config_id": config_oid,
                }
            )
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
                        extraction_status=(
                            training.get("extraction_status") if training else None
                        ),
                        feature_count=(
                            training.get("feature_count", 0) if training else 0
                        ),
                        extraction_error=(
                            training.get("extraction_error") if training else None
                        ),
                        missing_resources=(
                            training.get("missing_resources", []) if training else []
                        ),
                        predicted_label=(
                            training.get("predicted_label") if training else None
                        ),
                        prediction_confidence=(
                            training.get("prediction_confidence") if training else None
                        ),
                        prediction_status=(
                            training.get("prediction_status", "pending")
                            if training
                            else None
                        ),
                        prediction_error=(
                            training.get("prediction_error") if training else None
                        ),
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
        Get detailed build info by ModelTrainingBuild._id.

        Features are fetched from FeatureVector (single source of truth).

        Args:
            build_id: ModelTrainingBuild._id (MongoDB ObjectId string)
        """
        from app.repositories.feature_vector import FeatureVectorRepository

        try:
            oid = ObjectId(build_id)
        except Exception:
            return None

        # Find TrainingBuild by ID
        training = self.model_training_build_repo.find_by_id(oid)
        if not training or not training.raw_build_run_id:
            return None

        # Get RawBuildRun from training build
        raw = self.raw_build_run_repo.find_by_id(training.raw_build_run_id)
        if not raw:
            return None

        training_dict = training.model_dump()

        # Get features from FeatureVector (single source of truth)
        features = {}
        feature_count = 0
        if training and training.feature_vector_id:
            fv_repo = FeatureVectorRepository(self.db)
            fv = fv_repo.find_by_id(training.feature_vector_id)
            if fv:
                features = fv.features or {}
                feature_count = fv.feature_count or len(features)

        return BuildDetail(
            _id=str(raw.id),
            build_number=raw.build_number,
            build_id=raw.ci_run_id or "",
            conclusion=raw.conclusion or "unknown",
            commit_sha=raw.commit_sha or "",
            branch=raw.branch or "",
            commit_message=raw.commit_message,
            commit_author=raw.commit_author,
            created_at=raw.created_at,
            completed_at=raw.completed_at,
            duration_seconds=raw.duration_seconds,
            web_url=raw.web_url,
            provider=raw.provider or "github_actions",
            logs_available=raw.logs_available,
            logs_expired=raw.logs_expired or False,
            # Training enrichment
            has_training_data=training_dict is not None,
            training_build_id=str(training.id) if training else None,
            extraction_status=(
                training_dict.get("extraction_status") if training_dict else None
            ),
            feature_count=feature_count,
            extraction_error=(
                training_dict.get("extraction_error") if training_dict else None
            ),
            features=features,
            # Prediction results
            predicted_label=(
                training_dict.get("predicted_label") if training_dict else None
            ),
            prediction_confidence=(
                training_dict.get("prediction_confidence") if training_dict else None
            ),
            prediction_uncertainty=(
                training_dict.get("prediction_uncertainty") if training_dict else None
            ),
            predicted_at=training_dict.get("predicted_at") if training_dict else None,
            prediction_status=(
                training_dict.get("prediction_status") if training_dict else None
            ),
            prediction_error=(
                training_dict.get("prediction_error") if training_dict else None
            ),
        )

    def get_recent_builds(
        self, limit: int = 10, current_user: dict = None
    ) -> List[BuildSummary]:
        """Get most recent builds across repos accessible to user.

        Only returns builds from IMPORTED repositories (status='imported').
        - Admin: sees all imported repos
        - User: sees only repos in their github_accessible_repos that are imported
        """
        user_role = current_user.get("role", "user") if current_user else "admin"
        accessible_repos = (
            current_user.get("github_accessible_repos", []) if current_user else []
        )

        # Build repository filter - MUST be imported repos
        repo_filter: dict = {"status": "imported"}

        # For non-admin users, also filter by accessible repos
        if user_role != "admin" and accessible_repos:
            repo_filter["full_name"] = {"$in": accessible_repos}
        elif user_role != "admin" and not accessible_repos:
            # User has no accessible repos, return empty
            return []

        # Get raw_repo_ids from imported repositories only
        repos = list(self.db.repositories.find(repo_filter, {"raw_repo_id": 1}))
        raw_repo_ids = [r["raw_repo_id"] for r in repos if r.get("raw_repo_id")]

        if not raw_repo_ids:
            # No imported repos found, return empty
            return []

        # Query raw_build_runs filtered by imported repos
        query = {"raw_repo_id": {"$in": raw_repo_ids}}

        raw_cursor = (
            self.db.raw_build_runs.find(query).sort("created_at", -1).limit(limit)
        )
        raw_builds = list(raw_cursor)

        if not raw_builds:
            return []

        # Get training data (predictions)
        raw_ids = [b["_id"] for b in raw_builds]
        training_cursor = self.db.model_training_builds.find(
            {"raw_build_run_id": {"$in": raw_ids}}
        )
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
                    extraction_status=(
                        training.get("extraction_status") if training else None
                    ),
                    feature_count=training.get("feature_count", 0) if training else 0,
                    extraction_error=(
                        training.get("extraction_error") if training else None
                    ),
                    missing_resources=(
                        training.get("missing_resources", []) if training else []
                    ),
                    # Add prediction fields
                    predicted_label=(
                        training.get("predicted_label") if training else None
                    ),
                    prediction_confidence=(
                        training.get("prediction_confidence") if training else None
                    ),
                )
            )
        return items

    def get_import_builds(
        self,
        repo_id: str,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        status: Optional[str] = None,
    ) -> ImportBuildListResponse:
        """
        Get import/ingestion builds for a repository.

        Shows ModelImportBuild data with RawBuildRun enrichment.
        This is for the Ingestion phase.
        """
        from app.dtos.build import (
            ImportBuildListResponse,
            ImportBuildSummary,
            ResourceStatusDTO,
        )

        try:
            config_oid = ObjectId(repo_id)
        except Exception:
            return ImportBuildListResponse(items=[], total=0, page=1, size=limit)

        config = self.model_repo_config_repo.find_by_id(repo_id)
        if not config:
            return ImportBuildListResponse(items=[], total=0, page=1, size=limit)

        # Query model_import_builds
        match_query: Dict[str, Any] = {"model_repo_config_id": config_oid}

        if status:
            match_query["status"] = status

        if q:
            or_conditions = []
            or_conditions.append({"commit_sha": {"$regex": q, "$options": "i"}})
            or_conditions.append({"ci_run_id": {"$regex": q, "$options": "i"}})
            if or_conditions:
                match_query["$or"] = or_conditions

        total = self.db.model_import_builds.count_documents(match_query)

        # Use aggregation to sort by RawBuildRun.created_at
        pipeline = [
            {"$match": match_query},
            # Join with raw_build_runs to get created_at for sorting
            {
                "$lookup": {
                    "from": "raw_build_runs",
                    "localField": "raw_build_run_id",
                    "foreignField": "_id",
                    "as": "raw_build_run",
                }
            },
            {"$unwind": {"path": "$raw_build_run", "preserveNullAndEmptyArrays": True}},
            # Sort by RawBuildRun.created_at (build creation time on CI)
            {"$sort": {"raw_build_run.created_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
        ]

        import_builds = list(self.db.model_import_builds.aggregate(pipeline))

        if not import_builds:
            return ImportBuildListResponse(
                items=[], total=total, page=skip // limit + 1, size=limit
            )

        items = []
        for imp in import_builds:
            raw = imp.get("raw_build_run", {})

            # Convert resource_status dict
            resource_status = {}
            for key, val in imp.get("resource_status", {}).items():
                if isinstance(val, dict):
                    resource_status[key] = ResourceStatusDTO(
                        status=val.get("status", "pending"),
                        error=val.get("error"),
                    )

            items.append(
                ImportBuildSummary(
                    _id=str(imp["_id"]),
                    build_number=raw.get("build_number"),
                    build_id=raw.get("ci_run_id", ""),
                    commit_sha=imp.get("commit_sha") or raw.get("commit_sha", ""),
                    branch=raw.get("branch", ""),
                    conclusion=raw.get("conclusion", "unknown"),
                    created_at=raw.get("created_at"),
                    web_url=raw.get("web_url"),
                    commit_message=raw.get("commit_message"),
                    commit_author=raw.get("commit_author"),
                    duration_seconds=raw.get("duration_seconds"),
                    status=imp.get("status", "fetched"),
                    ingestion_started_at=imp.get("ingestion_started_at"),
                    ingested_at=imp.get("ingested_at"),
                    resource_status=resource_status,
                    required_resources=imp.get("required_resources", []),
                )
            )

        return ImportBuildListResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
        )

    def get_training_builds(
        self,
        repo_id: str,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        extraction_status: Optional[str] = None,
    ) -> TrainingBuildListResponse:
        """
        Get training/processing builds for a repository.

        Shows ModelTrainingBuild data with extraction and prediction info.
        This is for the Processing phase.
        """
        from app.dtos.build import TrainingBuildListResponse, TrainingBuildSummary

        try:
            config_oid = ObjectId(repo_id)
        except Exception:
            return TrainingBuildListResponse(items=[], total=0, page=1, size=limit)

        config = self.model_repo_config_repo.find_by_id(repo_id)
        if not config:
            return TrainingBuildListResponse(items=[], total=0, page=1, size=limit)

        # Query model_training_builds
        query: Dict[str, Any] = {"model_repo_config_id": config_oid}

        if extraction_status:
            query["extraction_status"] = extraction_status

        if q:
            or_conditions = []
            if q.isdigit():
                or_conditions.append({"build_number": int(q)})
            or_conditions.append({"head_sha": {"$regex": q, "$options": "i"}})
            if or_conditions:
                query["$or"] = or_conditions

        total = self.db.model_training_builds.count_documents(query)
        cursor = (
            self.db.model_training_builds.find(query)
            .sort("build_created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        training_builds = list(cursor)

        if not training_builds:
            return TrainingBuildListResponse(
                items=[], total=total, page=skip // limit + 1, size=limit
            )

        # Get RawBuildRun data for enrichment
        raw_ids = [t["raw_build_run_id"] for t in training_builds]
        raw_cursor = self.db.raw_build_runs.find({"_id": {"$in": raw_ids}})
        raw_map = {doc["_id"]: doc for doc in raw_cursor}

        # Get FeatureVector data for skipped_features and missing_resources
        fv_ids = [
            t["feature_vector_id"]
            for t in training_builds
            if t.get("feature_vector_id")
        ]
        fv_cursor = self.db.feature_vectors.find({"_id": {"$in": fv_ids}})
        fv_map = {doc["_id"]: doc for doc in fv_cursor}

        items = []
        for training in training_builds:
            raw = raw_map.get(training["raw_build_run_id"], {})
            fv = fv_map.get(training.get("feature_vector_id"), {})

            items.append(
                TrainingBuildSummary(
                    _id=str(training["_id"]),
                    build_number=training.get("build_number")
                    or raw.get("build_number"),
                    build_id=raw.get("ci_run_id", ""),
                    commit_sha=training.get("head_sha") or raw.get("commit_sha", ""),
                    branch=raw.get("branch", ""),
                    conclusion=raw.get("conclusion", "unknown"),
                    created_at=training.get("build_created_at")
                    or raw.get("created_at"),
                    web_url=raw.get("web_url"),
                    extraction_status=training.get("extraction_status", "pending"),
                    extraction_error=training.get("extraction_error"),
                    extracted_at=training.get("extracted_at"),
                    feature_count=fv.get("feature_count", 0)
                    or len(fv.get("features", {})),
                    skipped_features=fv.get("skipped_features", []),
                    missing_resources=fv.get("missing_resources", []),
                    predicted_label=training.get("predicted_label"),
                    prediction_confidence=training.get("prediction_confidence"),
                    prediction_uncertainty=training.get("prediction_uncertainty"),
                    predicted_at=training.get("predicted_at"),
                    prediction_status=training.get("prediction_status", "pending"),
                    prediction_error=training.get("prediction_error"),
                )
            )

        return TrainingBuildListResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
        )

    def get_unified_builds(
        self,
        repo_id: str,
        skip: int = 0,
        limit: int = 20,
        q: Optional[str] = None,
        phase_filter: Optional[str] = None,
    ):
        """
        Get unified builds combining ingestion + processing data.

        Uses LEFT JOIN to include builds with/without processing data.
        Primary source is ModelImportBuild, enriched with:
        - RawBuildRun for CI metadata
        - ModelTrainingBuild for extraction/prediction data (optional)

        Args:
            repo_id: ModelRepoConfig._id
            skip: Pagination offset
            limit: Page size
            q: Search query (build number, commit sha)
            phase_filter: Filter by phase ("ingestion", "processing", "prediction")

        Returns:
            UnifiedBuildListResponse with combined data
        """
        from app.dtos.build import (
            ResourceStatusDTO,
            UnifiedBuildListResponse,
            UnifiedBuildSummary,
        )

        try:
            config_oid = ObjectId(repo_id)
        except Exception:
            return UnifiedBuildListResponse(items=[], total=0, page=1, size=limit)

        repo_config = self.model_repo_config_repo.find_by_id(repo_id)
        if not repo_config:
            return UnifiedBuildListResponse(items=[], total=0, page=1, size=limit)

        # Build match query for model_import_builds
        match_query: Dict[str, Any] = {"model_repo_config_id": config_oid}

        # Apply search filter
        if q:
            search_conditions = []
            if q.isdigit():
                search_conditions.append({"raw_build_run.build_number": int(q)})
            search_conditions.append({"commit_sha": {"$regex": q, "$options": "i"}})
            search_conditions.append({"ci_run_id": {"$regex": q, "$options": "i"}})
            match_query["$or"] = search_conditions

        # Apply phase filter
        if phase_filter == "ingestion":
            # Only builds still in ingestion phase (not yet processed)
            match_query["status"] = {
                "$in": ["pending", "fetched", "ingesting", "ingested"]
            }
        elif phase_filter == "processing":
            # Only builds with processing data (has training_build)
            # This will be filtered after the join
            pass
        elif phase_filter == "prediction":
            # Only builds with prediction data
            pass

        # Aggregation pipeline with LEFT JOINs
        pipeline = [
            {"$match": match_query},
            # Join with raw_build_runs for CI metadata
            {
                "$lookup": {
                    "from": "raw_build_runs",
                    "localField": "raw_build_run_id",
                    "foreignField": "_id",
                    "as": "raw_build_run",
                }
            },
            {"$unwind": {"path": "$raw_build_run", "preserveNullAndEmptyArrays": True}},
            # LEFT JOIN with model_training_builds (optional - only after processing)
            {
                "$lookup": {
                    "from": "model_training_builds",
                    "localField": "_id",
                    "foreignField": "model_import_build_id",
                    "as": "training_build",
                }
            },
            {
                "$unwind": {
                    "path": "$training_build",
                    "preserveNullAndEmptyArrays": True,
                }
            },
            # LEFT JOIN with feature_vectors for feature counts
            {
                "$lookup": {
                    "from": "feature_vectors",
                    "localField": "training_build.feature_vector_id",
                    "foreignField": "_id",
                    "as": "feature_vector",
                }
            },
            {
                "$unwind": {
                    "path": "$feature_vector",
                    "preserveNullAndEmptyArrays": True,
                }
            },
            # Sort by build creation time (newest first)
            {"$sort": {"raw_build_run.created_at": -1}},
        ]

        # Apply phase filter in pipeline if needed
        if phase_filter == "processing":
            pipeline.append(
                {"$match": {"training_build": {"$exists": True, "$ne": None}}}
            )
        elif phase_filter == "prediction":
            pipeline.append(
                {
                    "$match": {
                        "training_build.prediction_status": {
                            "$in": ["completed", "failed"]
                        }
                    }
                }
            )

        # Count total before pagination (for accurate count with phase filter)
        count_pipeline = pipeline.copy()
        count_pipeline.append({"$count": "total"})
        count_result = list(self.db.model_import_builds.aggregate(count_pipeline))
        total_count = count_result[0]["total"] if count_result else 0

        # Add pagination
        pipeline.append({"$skip": skip})
        pipeline.append({"$limit": limit})

        unified_builds = list(self.db.model_import_builds.aggregate(pipeline))

        if not unified_builds:
            return UnifiedBuildListResponse(
                items=[], total=total_count, page=skip // limit + 1, size=limit
            )

        unified_items = []
        for build_doc in unified_builds:
            raw_build = build_doc.get("raw_build_run", {})
            training_build = build_doc.get("training_build")
            feature_vector = build_doc.get("feature_vector", {})

            # Convert resource_status dict to DTOs
            resource_status_map = {}
            for resource_name, resource_data in build_doc.get(
                "resource_status", {}
            ).items():
                if isinstance(resource_data, dict):
                    resource_status_map[resource_name] = ResourceStatusDTO(
                        status=resource_data.get("status", "pending"),
                        error=resource_data.get("error"),
                    )

            unified_items.append(
                UnifiedBuildSummary(
                    _id=str(build_doc["_id"]),
                    build_number=raw_build.get("build_number"),
                    ci_run_id=raw_build.get("ci_run_id"),
                    commit_sha=build_doc.get("commit_sha")
                    or raw_build.get("commit_sha", ""),
                    branch=raw_build.get("branch", ""),
                    ci_conclusion=raw_build.get("conclusion", "unknown"),
                    created_at=raw_build.get("created_at"),
                    web_url=raw_build.get("web_url"),
                    commit_message=raw_build.get("commit_message"),
                    commit_author=raw_build.get("commit_author"),
                    # Phase 2: Ingestion
                    ingestion_status=build_doc.get("status", "pending"),
                    resource_status=resource_status_map,
                    required_resources=build_doc.get("required_resources", []),
                    # Phase 3: Extraction (optional)
                    training_build_id=(
                        str(training_build["_id"]) if training_build else None
                    ),
                    extraction_status=(
                        training_build.get("extraction_status")
                        if training_build
                        else None
                    ),
                    feature_count=feature_vector.get("feature_count", 0)
                    or len(feature_vector.get("features", {})),
                    extraction_error=(
                        training_build.get("extraction_error")
                        if training_build
                        else None
                    ),
                    # Phase 4: Prediction (optional)
                    prediction_status=(
                        training_build.get("prediction_status")
                        if training_build
                        else None
                    ),
                    predicted_label=(
                        training_build.get("predicted_label")
                        if training_build
                        else None
                    ),
                    prediction_confidence=(
                        training_build.get("prediction_confidence")
                        if training_build
                        else None
                    ),
                    prediction_uncertainty=(
                        training_build.get("prediction_uncertainty")
                        if training_build
                        else None
                    ),
                )
            )

        return UnifiedBuildListResponse(
            items=unified_items,
            total=total_count,
            page=skip // limit + 1,
            size=limit,
        )
