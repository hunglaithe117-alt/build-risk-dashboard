"""Filesystem helper for persisting downloaded workflow logs."""

from __future__ import annotations

from pathlib import Path
from typing import List

from app.config import settings


class ArtifactStore:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(root or settings.ARTIFACTS_ROOT)
        self.root.mkdir(parents=True, exist_ok=True)

    def _build_dir(self, build_id: int) -> Path:
        path = self.root / str(build_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def log_path(self, build_id: int, job_id: int) -> Path:
        return self._build_dir(build_id) / f"{job_id}.log"

    def write_job_log(self, build_id: int, job_id: int, content: str) -> Path:
        path = self.log_path(build_id, job_id)
        path.write_text(content, encoding="utf-8")
        return path

    def read_job_log(self, build_id: int, job_id: int) -> str:
        path = self.log_path(build_id, job_id)
        return path.read_text(encoding="utf-8")

    def list_job_logs(self, build_id: int) -> List[str]:
        directory = self.root / str(build_id)
        if not directory.exists():
            return []
        return [p.stem for p in directory.glob("*.log")]
