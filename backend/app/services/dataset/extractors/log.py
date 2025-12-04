"""
Log Feature Extractor.

Extracts features from build logs.
Matches implementation in extracts/build_log_extractor.py.
"""

import logging
from pathlib import Path
from typing import Set

from app.services.dataset.context import DatasetExtractionContext
from app.services.dataset.extractors.base import BaseFeatureExtractor
from app.services.extracts.log_parser import TestLogParser

logger = logging.getLogger(__name__)


class LogFeatureExtractor(BaseFeatureExtractor):
    """
    Extractor for features parsed from build logs.
    
    Requires log files to be downloaded and stored locally.
    Matches implementation in extracts/build_log_extractor.py.
    """
    
    SUPPORTED_FEATURES = {
        "tr_jobs",
        "tr_build_id",
        "tr_build_number",
        "tr_original_commit",
        "tr_log_lan_all",
        "tr_log_frameworks_all",
        "tr_log_num_jobs",
        "tr_log_tests_run_sum",
        "tr_log_tests_failed_sum",
        "tr_log_tests_skipped_sum",
        "tr_log_tests_ok_sum",
        "tr_log_tests_fail_rate",
        "tr_log_testduration_sum",
        "tr_status",
        "tr_duration",
    }
    
    def __init__(self, log_dir: Path):
        """
        Initialize log extractor.
        
        Args:
            log_dir: Directory where job logs are stored
        """
        self.log_dir = log_dir
        self.log_parser = TestLogParser()
    
    def extract(self, ctx: DatasetExtractionContext, features: Set[str]) -> None:
        """Extract features from build logs."""
        repo_id = str(ctx.repo.id)
        run_id = ctx.workflow_run.workflow_run_id
        
        # Check if logs exist, if not try to download them
        log_path = self.log_dir / repo_id / str(run_id)
        if not log_path.exists():
            # Try to download logs on-demand
            downloaded = self._download_logs_for_run(ctx, log_path)
            if not downloaded:
                ctx.add_warning(f"Logs not found and could not be downloaded for run {run_id}")
                return
        
        # Find all log files
        log_files = list(log_path.glob("*.log"))
        if not log_files:
            ctx.add_warning(f"No log files found for run {run_id}")
            return
        
        try:
            result = self._parse_all_logs(ctx, log_files)
            
            for name, value in result.items():
                if name in features:
                    ctx.add_feature(name, value)
                    
        except Exception as e:
            ctx.add_error(f"Log parsing failed: {e}")
            logger.error(f"Log parsing error for run {run_id}: {e}")
    
    def _parse_all_logs(self, ctx: DatasetExtractionContext, log_files: list) -> dict:
        """Parse all log files and aggregate results."""
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
                parsed = self.log_parser.parse(content)
                
                if parsed.framework:
                    frameworks.add(parsed.framework)
                
                tests_run_sum += parsed.tests_run
                tests_failed_sum += parsed.tests_failed
                tests_skipped_sum += parsed.tests_skipped
                tests_ok_sum += parsed.tests_ok
                
                if parsed.test_duration_seconds:
                    test_duration_sum += parsed.test_duration_seconds
                    
            except Exception as e:
                logger.warning(f"Failed to parse log {log_file}: {e}")
        
        # Calculate derived metrics
        fail_rate = tests_failed_sum / tests_run_sum if tests_run_sum > 0 else 0.0
        
        # Determine tr_status (matches build_log_extractor.py)
        tr_status = "passed"
        if ctx.workflow_run.conclusion == "failure":
            tr_status = "failed"
        elif ctx.workflow_run.conclusion == "cancelled":
            tr_status = "cancelled"
        elif tests_failed_sum > 0:
            tr_status = "failed"
        
        # Calculate total duration from workflow run timestamps
        tr_duration = 0.0
        if ctx.workflow_run.created_at and ctx.workflow_run.updated_at:
            delta = ctx.workflow_run.updated_at - ctx.workflow_run.created_at
            tr_duration = delta.total_seconds()
        
        return {
            "tr_jobs": tr_jobs,
            "tr_build_id": ctx.workflow_run.workflow_run_id,
            "tr_build_number": ctx.workflow_run.run_number,
            "tr_original_commit": ctx.workflow_run.head_sha,
            "tr_log_lan_all": ctx.source_languages,
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
    
    def _download_logs_for_run(
        self, 
        ctx: DatasetExtractionContext, 
        log_path: Path
    ) -> bool:
        """
        Download build logs for a workflow run on-demand.
        
        Args:
            ctx: Extraction context with repo and workflow run info
            log_path: Path where logs should be saved
            
        Returns:
            True if logs were downloaded successfully
        """
        import time
        from app.services.github.github_client import (
            get_app_github_client,
            get_public_github_client,
        )
        
        full_name = ctx.repo.full_name
        run_id = ctx.workflow_run.workflow_run_id
        installation_id = ctx.repo.installation_id
        
        try:
            # Use app client if available for higher rate limits
            client_context = (
                get_app_github_client(ctx.db, installation_id)
                if installation_id
                else get_public_github_client()
            )
            
            with client_context as gh:
                # Get jobs for this workflow run
                jobs = gh.list_workflow_jobs(full_name, run_id)
                
                if not jobs:
                    logger.warning(f"No jobs found for run {run_id}")
                    return False
                
                # Create log directory
                log_path.mkdir(parents=True, exist_ok=True)
                
                logs_downloaded = 0
                for job in jobs:
                    job_id = job.get("id")
                    if not job_id:
                        continue
                    
                    try:
                        log_content = gh.download_job_logs(full_name, job_id)
                        if log_content:
                            file_path = log_path / f"{job_id}.log"
                            with open(file_path, "wb") as f:
                                f.write(log_content)
                            logs_downloaded += 1
                            
                            # Small delay to avoid rate limiting
                            time.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"Failed to download logs for job {job_id}: {e}")
                        continue
                
                if logs_downloaded > 0:
                    logger.info(f"Downloaded {logs_downloaded} log files for run {run_id}")
                    return True
                else:
                    logger.warning(f"No logs could be downloaded for run {run_id}")
                    return False
                    
        except Exception as e:
            logger.error(f"Failed to download logs for run {run_id}: {e}")
            return False
