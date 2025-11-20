import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.models.entities.build_sample import BuildSample
from app.models.entities.imported_repository import ImportedRepository
from app.services.extracts.diff_analyzer import (
    _is_source_file,
    _is_test_file,
    _matches_test_definition,
)
from app.services.github.github_app import get_installation_token
from app.utils.locking import repo_lock
from pymongo.database import Database

logger = logging.getLogger(__name__)

REPOS_DIR = Path("repos")


class RepoSnapshotExtractor:
    def __init__(self, db: Database):
        self.db = db

    def extract(
        self, build_sample: BuildSample, repo: ImportedRepository
    ) -> Dict[str, Any]:
        commit_sha = build_sample.tr_original_commit
        if not commit_sha:
            return self._empty_result()

        repo_path = REPOS_DIR / str(repo.id)
        if not repo_path.exists():
            # Should have been cloned by diff extractor, but ensure it exists
            with repo_lock(str(repo.id)):
                self._ensure_repo(repo, repo_path)

        try:
            # 1. History metrics (Age, Num Commits)
            age, num_commits = self._get_history_metrics(repo_path, commit_sha)

            # 2. Snapshot metrics (SLOC, Tests) using worktree
            # Lock during worktree operations as they modify .git/worktrees
            with repo_lock(str(repo.id)):
                snapshot_metrics = self._analyze_snapshot(
                    repo_path, commit_sha, repo.main_lang
                )

            return {
                "gh_repo_age": age,
                "gh_repo_num_commits": num_commits,
                **snapshot_metrics,
            }

        except Exception as e:
            logger.error(
                f"Failed to extract snapshot features for {repo.full_name}: {e}"
            )
            return self._empty_result()

    def _ensure_repo(self, repo: ImportedRepository, repo_path: Path):
        # Simple clone if not exists (duplicate logic from diff extractor, could be shared)
        if repo_path.exists():
            return

        token = get_installation_token(repo.installation_id, self.db)
        auth_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
        subprocess.run(
            ["git", "clone", auth_url, str(repo_path)],
            check=True,
            capture_output=True,
        )

    def _run_git(self, cwd: Path, args: List[str]) -> str:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _get_history_metrics(
        self, repo_path: Path, commit_sha: str
    ) -> Tuple[float, int]:
        # Num commits
        # git rev-list --count <sha>
        try:
            count_out = self._run_git(repo_path, ["rev-list", "--count", commit_sha])
            num_commits = int(count_out)
        except (subprocess.CalledProcessError, ValueError):
            num_commits = 0

        # Age
        # First commit date vs current commit date
        try:
            # Current commit date
            current_ts = self._run_git(
                repo_path, ["show", "-s", "--format=%ct", commit_sha]
            )

            # First commit date (follow parent until end)
            # git rev-list --max-parents=0 <sha> (gets root commits reachable from sha)
            roots = self._run_git(
                repo_path, ["rev-list", "--max-parents=0", commit_sha]
            ).splitlines()
            if roots:
                # Use the oldest root if multiple
                root_sha = roots[-1]
                first_ts = self._run_git(
                    repo_path, ["show", "-s", "--format=%ct", root_sha]
                )

                age_seconds = int(current_ts) - int(first_ts)
                age_days = max(0.0, age_seconds / 86400.0)
            else:
                age_days = 0.0
        except (subprocess.CalledProcessError, ValueError):
            age_days = 0.0

        return age_days, num_commits

    def _analyze_snapshot(
        self, repo_path: Path, commit_sha: str, language: str | None
    ) -> Dict[str, int]:
        stats = {
            "gh_sloc": 0,
            "gh_test_lines": 0,
            "gh_test_cases": 0,
            "gh_asserts": 0,
        }

        # Create temporary worktree
        with tempfile.TemporaryDirectory() as tmp_dir:
            worktree_path = Path(tmp_dir) / "worktree"
            try:
                # git worktree add -f <path> <sha>
                # -f to force if branch is already checked out elsewhere (though we use SHA)
                # Detached HEAD is fine
                subprocess.run(
                    ["git", "worktree", "add", "-f", str(worktree_path), commit_sha],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                )

                # Walk files
                for file_path in worktree_path.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if ".git" in file_path.parts:
                        continue

                    rel_path = str(file_path.relative_to(worktree_path))

                    try:
                        # Count lines
                        # Use 'wc -l' or read file. Reading might be slow for huge repos but accurate.
                        # Let's read with error handling
                        with open(file_path, "r", errors="ignore") as f:
                            lines = f.readlines()
                            line_count = len(lines)
                            content = "".join(lines)

                        if _is_test_file(rel_path):
                            stats["gh_test_lines"] += line_count
                            stats["gh_test_cases"] += self._count_tests(
                                content, language
                            )
                            stats["gh_asserts"] += self._count_asserts(
                                content, language
                            )
                        elif _is_source_file(rel_path):
                            stats["gh_sloc"] += line_count

                    except Exception:
                        pass

            finally:
                # Cleanup worktree
                # git worktree remove <path>
                # Need to run this from main repo
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "-f", str(worktree_path)],
                        cwd=repo_path,
                        capture_output=True,
                    )
                    # Prune to be safe
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        cwd=repo_path,
                        capture_output=True,
                    )
                except Exception:
                    pass

        return stats

    def _count_tests(self, content: str, language: str | None) -> int:
        count = 0
        lang = (language or "").lower()
        for line in content.splitlines():
            if _matches_test_definition(line, lang):
                count += 1
        return count

    def _count_asserts(self, content: str, language: str | None) -> int:
        # Simple heuristic
        lang = (language or "").lower()
        lower_content = content.lower()
        if lang == "ruby":
            return lower_content.count("assert") + lower_content.count("expect(")
        # Python / Default
        return lower_content.count("assert")

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "gh_repo_age": 0.0,
            "gh_repo_num_commits": 0,
            "gh_sloc": 0,
            "gh_test_lines": 0,
            "gh_test_cases": 0,
            "gh_asserts": 0,
        }
