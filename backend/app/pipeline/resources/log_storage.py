"""
Log Storage Resource Provider.

Provides access to build logs stored on disk.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, TYPE_CHECKING

from app.pipeline.resources import ResourceProvider, ResourceNames

if TYPE_CHECKING:
    from app.pipeline.core.context import ExecutionContext

logger = logging.getLogger(__name__)

DEFAULT_LOG_DIR = Path("../repo-data/job_logs")


@dataclass
class LogFile:
    """Represents a job log file."""
    path: Path
    job_id: int
    content: Optional[str] = None
    
    def read(self) -> str:
        """Read log content (lazy loading)."""
        if self.content is None:
            self.content = self.path.read_text(errors="replace")
        return self.content


@dataclass 
class LogStorageHandle:
    """Handle to build log storage."""
    log_dir: Path
    repo_id: str
    run_id: int
    log_files: List[LogFile]
    
    @property
    def has_logs(self) -> bool:
        return len(self.log_files) > 0
    
    def get_all_content(self) -> str:
        """Get concatenated content of all logs."""
        return "\n".join(lf.read() for lf in self.log_files)


class LogStorageProvider(ResourceProvider):
    """
    Provides access to downloaded job logs.
    """
    
    def __init__(self, log_dir: Path = DEFAULT_LOG_DIR):
        self.log_dir = log_dir
    
    @property
    def name(self) -> str:
        return ResourceNames.LOG_STORAGE
    
    def initialize(self, context: "ExecutionContext") -> LogStorageHandle:
        build_sample = context.build_sample
        
        repo_id = str(build_sample.repo_id)
        run_id = build_sample.workflow_run_id
        
        run_log_dir = self.log_dir / repo_id / str(run_id)
        
        log_files = []
        if run_log_dir.exists():
            for log_path in run_log_dir.glob("*.log"):
                try:
                    job_id = int(log_path.stem)
                    log_files.append(LogFile(path=log_path, job_id=job_id))
                except ValueError:
                    logger.warning(f"Unexpected log file name: {log_path}")
        
        return LogStorageHandle(
            log_dir=run_log_dir,
            repo_id=repo_id,
            run_id=run_id,
            log_files=log_files,
        )
