import logging
from pathlib import Path
from typing import Any, Dict

from app.entities.build_sample import BuildSample
from app.entities.imported_repository import ImportedRepository
from app.entities.workflow_run import WorkflowRunRaw
from app.services.extracts.log_parser import TestLogParser

logger = logging.getLogger(__name__)


class BuildLogExtractor:
    def __init__(self, log_dir: Path = Path("../repo-data/job_logs")):
        self.log_dir = log_dir
        self.parser = TestLogParser()

    def extract(
        self,
        build_sample: BuildSample,
        workflow_run: WorkflowRunRaw,
        repo: ImportedRepository,
    ) -> Dict[str, Any]:
        repo_id = str(build_sample.repo_id)
        run_id = str(build_sample.workflow_run_id)

        # Locate logs
        run_log_dir = self.log_dir / repo_id / run_id
        if not run_log_dir.exists():
            logger.warning(f"No logs found for {repo_id}/{run_id}")
            return self._empty_result()

        log_files = list(run_log_dir.glob("*.log"))
        if not log_files:
            logger.warning(f"No log files found in {run_log_dir}")
            return self._empty_result()

        # Initialize aggregators
        tr_jobs = []
        frameworks = set()
        total_jobs = 0
        tests_run_sum = 0
        tests_failed_sum = 0
        tests_skipped_sum = 0
        tests_ok_sum = 0
        test_duration_sum = 0.0

        for log_file in log_files:
            try:
                job_id = int(log_file.stem)
                tr_jobs.append(job_id)
                total_jobs += 1

                content = log_file.read_text(errors="replace")

                # Parse log with user-selected framework hints
                allowed_frameworks = [
                    f.value.lower() if hasattr(f, "value") else str(f).lower()
                    for f in getattr(repo, "test_frameworks", []) or []
                ]
                language_hint = None
                if repo.source_languages:
                    lang = repo.source_languages[0]
                    language_hint = lang.lower() if isinstance(lang, str) else str(lang).lower()
                parsed = self.parser.parse(
                    content,
                    language_hint=language_hint,
                    allowed_frameworks=allowed_frameworks or None,
                )

                if parsed.framework:
                    frameworks.add(parsed.framework)

                tests_run_sum += parsed.tests_run
                tests_failed_sum += parsed.tests_failed
                tests_skipped_sum += parsed.tests_skipped
                tests_ok_sum += parsed.tests_ok

                if parsed.test_duration_seconds:
                    test_duration_sum += parsed.test_duration_seconds

            except Exception as e:
                logger.error(f"Failed to parse log {log_file}: {e}")

        # Calculate derived metrics
        fail_rate = 0.0
        if tests_run_sum > 0:
            fail_rate = tests_failed_sum / tests_run_sum

        # Determine tr_status
        tr_status = "passed"
        if workflow_run.conclusion == "failure":
            tr_status = "failed"
        elif workflow_run.conclusion == "cancelled":
            tr_status = "cancelled"
        elif tests_failed_sum > 0:
            tr_status = "failed"

        # Calculate total duration from workflow run timestamps
        tr_duration = 0.0
        if workflow_run.created_at and workflow_run.updated_at:
            delta = workflow_run.updated_at - workflow_run.created_at
            tr_duration = delta.total_seconds()

        return {
            "tr_jobs": tr_jobs,
            "tr_build_id": workflow_run.workflow_run_id,
            "tr_build_number": workflow_run.run_number,
            "tr_original_commit": workflow_run.head_sha,
            "tr_log_lan_all": repo.source_languages,
            "tr_log_frameworks_all": list(frameworks),
            "tr_log_num_jobs": total_jobs,
            "tr_log_tests_run_sum": tests_run_sum,
            "tr_log_tests_failed_sum": tests_failed_sum,
            "tr_log_tests_skipped_sum": tests_skipped_sum,
            "tr_log_tests_ok_sum": tests_ok_sum,
            "tr_log_tests_fail_rate": fail_rate,
            "tr_log_testduration_sum": test_duration_sum,
            "tr_status": tr_status,
            "tr_duration": tr_duration,
        }

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "tr_jobs": [],
            "tr_build_id": None,
            "tr_build_number": None,
            "tr_original_commit": None,
            "tr_log_lan_all": [],
            "tr_log_frameworks_all": [],
            "tr_log_num_jobs": 0,
            "tr_log_tests_run_sum": 0,
            "tr_log_tests_failed_sum": 0,
            "tr_log_tests_skipped_sum": 0,
            "tr_log_tests_ok_sum": 0,
            "tr_log_tests_fail_rate": 0.0,
            "tr_log_testduration_sum": 0.0,
            "tr_status": "unknown",
            "tr_duration": 0.0,
        }
