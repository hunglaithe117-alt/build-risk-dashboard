from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.dtos.build import BuildDetail, BuildListResponse, BuildSummary
from app.entities.build_sample import BuildSample
from app.entities.workflow_run import WorkflowRunRaw


class BuildService:
    def __init__(self, db: Database):
        self.db = db
        self.build_collection = db["build_samples"]
        self.workflow_collection = db["workflow_runs"]

    def _get_feature(self, sample: BuildSample, key: str, default=None):
        """Helper to get feature value from sample.features dict."""
        return sample.features.get(key, default) if sample.features else default

    def get_builds_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 20, q: Optional[str] = None
    ) -> BuildListResponse:
        query = {"repo_id": ObjectId(repo_id)}

        if q:
            or_conditions = []
            if q.isdigit():
                or_conditions.append({"features.tr_build_number": int(q)})

            or_conditions.append({"features.tr_original_commit": {"$regex": q, "$options": "i"}})
            or_conditions.append({"status": {"$regex": q, "$options": "i"}})

            query["$or"] = or_conditions

        total = self.build_collection.count_documents(query)
        cursor = (
            self.build_collection.find(query)
            .sort("features.tr_build_number", -1)
            .skip(skip)
            .limit(limit)
        )

        build_samples = [BuildSample(**doc) for doc in cursor]

        if not build_samples:
            return BuildListResponse(
                items=[], total=total, page=skip // limit + 1, size=limit
            )

        # Fetch workflow runs
        workflow_run_ids = [b.workflow_run_id for b in build_samples]
        workflow_runs_cursor = self.workflow_collection.find(
            {"workflow_run_id": {"$in": workflow_run_ids}}
        )
        workflow_runs = {
            w["workflow_run_id"]: WorkflowRunRaw(**w) for w in workflow_runs_cursor
        }

        items = []
        for sample in build_samples:
            workflow = workflow_runs.get(sample.workflow_run_id)

            items.append(
                BuildSummary(
                    _id=str(sample.id),
                    build_number=self._get_feature(sample, "tr_build_number", 0),
                    status=self._get_feature(sample, "tr_status", "unknown"),
                    extraction_status=sample.status,
                    commit_sha=self._get_feature(sample, "tr_original_commit")
                    or (workflow.head_sha if workflow else ""),
                    created_at=workflow.created_at if workflow else None,
                    duration=self._get_feature(sample, "tr_duration"),
                    num_jobs=self._get_feature(sample, "tr_log_num_jobs"),
                    num_tests=self._get_feature(sample, "tr_log_tests_run_sum"),
                    workflow_run_id=sample.workflow_run_id,
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

        sample = BuildSample(**doc)
        workflow_doc = self.workflow_collection.find_one(
            {"workflow_run_id": sample.workflow_run_id}
        )
        workflow = WorkflowRunRaw(**workflow_doc) if workflow_doc else None

        return BuildDetail(
            _id=str(sample.id),
            build_number=self._get_feature(sample, "tr_build_number", 0),
            status=self._get_feature(sample, "tr_status", "unknown"),
            extraction_status=sample.status,
            commit_sha=self._get_feature(sample, "tr_original_commit")
            or (workflow.head_sha if workflow else ""),
            created_at=workflow.created_at if workflow else None,
            duration=self._get_feature(sample, "tr_duration"),
            num_jobs=self._get_feature(sample, "tr_log_num_jobs"),
            num_tests=self._get_feature(sample, "tr_log_tests_run_sum"),
            workflow_run_id=sample.workflow_run_id,
            features=sample.features,
            error_message=sample.error_message,
        )

    def get_recent_builds(self, limit: int = 10) -> List[BuildSummary]:
        cursor = self.build_collection.find({}).sort("_id", -1).limit(limit)

        build_samples = [BuildSample(**doc) for doc in cursor]
        if not build_samples:
            return []

        # Fetch workflow runs
        workflow_run_ids = [b.workflow_run_id for b in build_samples]
        workflow_runs_cursor = self.workflow_collection.find(
            {"workflow_run_id": {"$in": workflow_run_ids}}
        )
        workflow_runs = {
            w["workflow_run_id"]: WorkflowRunRaw(**w) for w in workflow_runs_cursor
        }

        items = []
        for sample in build_samples:
            workflow = workflow_runs.get(sample.workflow_run_id)

            items.append(
                BuildSummary(
                    _id=str(sample.id),
                    build_number=self._get_feature(sample, "tr_build_number", 0),
                    status=self._get_feature(sample, "tr_status", "unknown"),
                    extraction_status=sample.status,
                    commit_sha=self._get_feature(sample, "tr_original_commit")
                    or (workflow.head_sha if workflow else ""),
                    created_at=workflow.created_at if workflow else None,
                    duration=self._get_feature(sample, "tr_duration"),
                    num_jobs=self._get_feature(sample, "tr_log_num_jobs"),
                    num_tests=self._get_feature(sample, "tr_log_tests_run_sum"),
                    workflow_run_id=sample.workflow_run_id,
                )
            )
        return items

    def trigger_sonar_scan_direct(self, build_id: str):
        from app.tasks.sonar import run_sonar_scan

        # Verify build exists
        if not self.build_collection.find_one({"_id": ObjectId(build_id)}):
            raise ValueError("Build not found")

        # Trigger Celery task
        run_sonar_scan.delay(build_id)

        # Update status
        self.build_collection.update_one(
            {"_id": ObjectId(build_id)}, {"$set": {"sonar_scan_status": "queued"}}
        )
        return True

