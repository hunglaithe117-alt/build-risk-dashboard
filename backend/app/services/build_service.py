from typing import List, Optional, Any

from bson import ObjectId
from pymongo.database import Database

from app.dtos.build import BuildDetail, BuildListResponse, BuildSummary
from app.entities.model_training_build import ModelTrainingBuild
from app.entities.raw_build_run import RawBuildRun


class BuildService:
    def __init__(self, db: Database):
        self.db = db
        self.build_collection = db["model_training_builds"]
        self.build_runs_collection = db["raw_build_runs"]

    def _get_feature(self, sample: Any, key: str, default=None):
        """Helper to get feature value from sample.features dict."""
        features = getattr(sample, "features", None) or {}
        return features.get(key, default)

    def get_builds_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 20, q: Optional[str] = None
    ) -> BuildListResponse:
        query = {"raw_repo_id": ObjectId(repo_id)}

        if q:
            or_conditions = []
            if q.isdigit():
                or_conditions.append({"features.tr_build_number": int(q)})

            or_conditions.append(
                {"features.tr_original_commit": {"$regex": q, "$options": "i"}}
            )
            or_conditions.append({"build_conclusion": {"$regex": q, "$options": "i"}})

            query["$or"] = or_conditions

        total = self.build_collection.count_documents(query)
        cursor = (
            self.build_collection.find(query)
            .sort("build_created_at", -1)
            .skip(skip)
            .limit(limit)
        )

        build_samples = [ModelTrainingBuild(**doc) for doc in cursor]

        if not build_samples:
            return BuildListResponse(
                items=[], total=total, page=skip // limit + 1, size=limit
            )

        build_run_ids = [b.raw_workflow_run_id for b in build_samples]
        build_runs_cursor = self.build_runs_collection.find(
            {"_id": {"$in": build_run_ids}}
        )
        build_runs = {w["_id"]: RawBuildRun(**w) for w in build_runs_cursor}

        items = []
        for sample in build_samples:
            build_run = build_runs.get(sample.raw_workflow_run_id)

            items.append(
                BuildSummary(
                    _id=str(sample.id),
                    build_number=sample.build_number,
                    status=sample.build_conclusion or "unknown",
                    extraction_status=sample.extraction_status,
                    commit_sha=sample.head_sha,
                    created_at=build_run.created_at if build_run else None,
                    workflow_run_id=build_run.build_id if build_run else None,
                    duration=self._get_feature(sample, "tr_duration"),
                    num_jobs=self._get_feature(sample, "tr_log_num_jobs"),
                    num_tests=self._get_feature(sample, "tr_log_tests_run_sum"),
                    logs_available=build_run.logs_available if build_run else None,
                    logs_expired=build_run.logs_expired if build_run else None,
                )
            )

        return BuildListResponse(
            items=items,
            total=total,
            page=skip // limit + 1,
            size=limit,
        )

    def get_build_detail(self, build_id: str) -> Optional[BuildDetail]:
        doc = self.build_collection.find_one({"_id": ObjectId(build_id)})
        if not doc:
            return None

        sample = ModelTrainingBuild(**doc)
        build_run_doc = self.build_runs_collection.find_one(
            {"_id": sample.raw_workflow_run_id}
        )
        build_run = RawBuildRun(**build_run_doc) if build_run_doc else None

        return BuildDetail(
            _id=str(sample.id),
            build_number=sample.build_number
            or self._get_feature(sample, "tr_build_number", 0),
            status=sample.build_conclusion
            or self._get_feature(sample, "tr_status", "unknown"),
            extraction_status=sample.extraction_status,
            commit_sha=sample.head_sha
            or self._get_feature(sample, "tr_original_commit")
            or "",
            created_at=build_run.created_at if build_run else None,
            duration=self._get_feature(sample, "tr_duration"),
            num_jobs=self._get_feature(sample, "tr_log_num_jobs"),
            num_tests=self._get_feature(sample, "tr_log_tests_run_sum"),
            workflow_run_id=build_run.build_id if build_run else None,
            features=sample.features,
            error_message=sample.extraction_error,
        )

    def get_recent_builds(self, limit: int = 10) -> List[BuildSummary]:
        cursor = self.build_collection.find({}).sort("_id", -1).limit(limit)

        build_samples = [ModelTrainingBuild(**doc) for doc in cursor]
        if not build_samples:
            return []

        # Fetch build runs
        build_run_ids = [b.raw_workflow_run_id for b in build_samples]
        build_runs_cursor = self.build_runs_collection.find(
            {"_id": {"$in": build_run_ids}}
        )
        build_runs = {w["_id"]: RawBuildRun(**w) for w in build_runs_cursor}

        items = []
        for sample in build_samples:
            build_run = build_runs.get(sample.raw_workflow_run_id)

            items.append(
                BuildSummary(
                    _id=str(sample.id),
                    build_number=sample.build_number
                    or self._get_feature(sample, "tr_build_number", 0),
                    status=sample.build_conclusion
                    or self._get_feature(sample, "tr_status", "unknown"),
                    extraction_status=sample.extraction_status,
                    commit_sha=sample.head_sha
                    or self._get_feature(sample, "tr_original_commit")
                    or "",
                    created_at=build_run.created_at if build_run else None,
                    duration=self._get_feature(sample, "tr_duration"),
                    num_jobs=self._get_feature(sample, "tr_log_num_jobs"),
                    num_tests=self._get_feature(sample, "tr_log_tests_run_sum"),
                    workflow_run_id=build_run.build_id if build_run else None,
                )
            )
        return items
