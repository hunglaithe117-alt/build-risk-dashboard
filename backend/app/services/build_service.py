from typing import List, Optional

from bson import ObjectId
from pymongo.database import Database

from app.dtos.build import BuildDetail, BuildListResponse, BuildSummary
from app.models.entities.build_sample import BuildSample
from app.models.entities.workflow_run import WorkflowRunRaw


class BuildService:
    def __init__(self, db: Database):
        self.db = db
        self.build_collection = db["build_samples"]
        self.workflow_collection = db["workflow_runs"]

    def get_builds_by_repo(
        self, repo_id: str, skip: int = 0, limit: int = 20
    ) -> BuildListResponse:
        query = {"repo_id": ObjectId(repo_id)}

        total = self.build_collection.count_documents(query)
        cursor = (
            self.build_collection.find(query)
            .sort("tr_build_number", -1)
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
                    build_number=sample.tr_build_number or 0,
                    status=sample.tr_status or "unknown",
                    extraction_status=sample.status,
                    commit_sha=sample.tr_original_commit
                    or (workflow.head_sha if workflow else ""),
                    created_at=workflow.created_at if workflow else None,
                    duration=sample.tr_duration,
                    num_jobs=sample.tr_log_num_jobs,
                    num_tests=sample.tr_log_tests_run_sum,
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
            build_number=sample.tr_build_number or 0,
            status=sample.tr_status or "unknown",
            extraction_status=sample.status,
            commit_sha=sample.tr_original_commit
            or (workflow.head_sha if workflow else ""),
            created_at=workflow.created_at if workflow else None,
            duration=sample.tr_duration,
            num_jobs=sample.tr_log_num_jobs,
            num_tests=sample.tr_log_tests_run_sum,
            workflow_run_id=sample.workflow_run_id,
            # Details
            git_diff_src_churn=sample.git_diff_src_churn,
            git_diff_test_churn=sample.git_diff_test_churn,
            gh_diff_files_added=sample.gh_diff_files_added,
            gh_diff_files_deleted=sample.gh_diff_files_deleted,
            gh_diff_files_modified=sample.gh_diff_files_modified,
            gh_diff_tests_added=sample.gh_diff_tests_added,
            gh_diff_tests_deleted=sample.gh_diff_tests_deleted,
            gh_repo_age=sample.gh_repo_age,
            gh_repo_num_commits=sample.gh_repo_num_commits,
            gh_sloc=sample.gh_sloc,
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
                    build_number=sample.tr_build_number or 0,
                    status=sample.tr_status or "unknown",
                    extraction_status=sample.status,
                    commit_sha=sample.tr_original_commit
                    or (workflow.head_sha if workflow else ""),
                    created_at=workflow.created_at if workflow else None,
                    duration=sample.tr_duration,
                    num_jobs=sample.tr_log_num_jobs,
                    num_tests=sample.tr_log_tests_run_sum,
                    workflow_run_id=sample.workflow_run_id,
                )
            )
        return items
