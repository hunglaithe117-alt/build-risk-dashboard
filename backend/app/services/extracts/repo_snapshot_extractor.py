import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.entities.build_sample import BuildSample
from app.entities.imported_repository import ImportedRepository
from app.entities.workflow_run import WorkflowRunRaw
from app.services.extracts.diff_analyzer import (
    _is_source_file,
    _is_test_file,
    _matches_test_definition,
    _matches_assertion,
    _strip_comments,
)
from app.services.github.github_app import get_installation_token
from app.utils.locking import repo_lock
from pymongo.database import Database
from app.services.commit_replay import ensure_commit_exists

logger = logging.getLogger(__name__)

REPOS_DIR = Path("../repo-data/repos")


class RepoSnapshotExtractor:
    def __init__(self, db: Database):
        self.db = db

    def extract(
        self,
        build_sample: BuildSample,
        workflow_run: WorkflowRunRaw,
        repo: ImportedRepository,
    ) -> Dict[str, Any]:
        commit_sha = build_sample.tr_original_commit
        if not commit_sha:
            return self._empty_result()

        # Extract metadata fields
        payload = workflow_run.raw_payload
        head_branch = payload.get("head_branch")
        pull_requests = payload.get("pull_requests", [])
        is_pr = len(pull_requests) > 0 or payload.get("event") == "pull_request"

        pr_number = None
        pr_created_at = None

        if pull_requests:
            pr_data = pull_requests[0]
            pr_number = pr_data.get("number")
            pr_created_at = pr_data.get("created_at")

        repo_path = REPOS_DIR / str(repo.id)
        if not repo_path.exists():
            # Should have been cloned by diff extractor, but ensure it exists
            with repo_lock(str(repo.id)):
                self._ensure_repo(repo, repo_path)

        # Ensure commit exists (handle forks)
        token = self._get_token(repo)
        effective_sha = ensure_commit_exists(
            repo_path, commit_sha, repo.full_name, token
        )

        if not effective_sha:
            logger.warning(f"Commit {commit_sha} not found in {repo.full_name}")
            result = self._empty_result()
            result["extraction_warning"] = (
                "Snapshot features missing: Commit not found (orphan/fork)"
            )
            return result

        try:
            # 1. History metrics (Age, Num Commits)
            age, num_commits = self._get_history_metrics(repo_path, effective_sha)

            # 2. Snapshot metrics (SLOC, Tests) using worktree
            # Lock during worktree operations as they modify .git/worktrees
            with repo_lock(str(repo.id)):
                for source_lang in repo.source_languages:
                    snapshot_metrics = self._analyze_snapshot(
                        repo_path, effective_sha, source_lang.value.lower()
                    )

            return {
                "gh_repo_age": age,
                "gh_repo_num_commits": num_commits,
                **snapshot_metrics,
                # Metadata fields
                "gh_project_name": repo.full_name,
                "gh_is_pr": is_pr,
                "gh_pr_created_at": pr_created_at,
                "gh_pull_req_num": pr_number,
                "gh_lang": repo.main_lang,
                "git_branch": head_branch,
                "git_trigger_commit": workflow_run.head_sha,
                "ci_provider": (
                    repo.ci_provider.value
                    if hasattr(repo.ci_provider, "value")
                    else repo.ci_provider
                ),
                "gh_build_started_at": workflow_run.created_at,
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

        auth_url = f"https://github.com/{repo.full_name}.git"
        token = self._get_token(repo)

        if token:
            if repo.installation_id:
                auth_url = (
                    f"https://x-access-token:{token}@github.com/{repo.full_name}.git"
                )
            else:
                auth_url = f"https://{token}@github.com/{repo.full_name}.git"

        logger.info(f"Cloning {repo.full_name} to {repo_path}")
        subprocess.run(
            ["git", "clone", auth_url, str(repo_path)],
            check=True,
            capture_output=True,
        )

    def _get_token(self, repo: ImportedRepository) -> str | None:
        if repo.installation_id:
            return get_installation_token(repo.installation_id, self.db)
        else:
            from app.config import settings

            tokens = settings.GITHUB_TOKENS
            if tokens and tokens[0]:
                return tokens[0]
        return None

    def _run_git(self, cwd: Path, args: List[str]) -> str:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    def _commit_exists(self, cwd: Path, sha: str) -> bool:
        try:
            subprocess.run(
                ["git", "cat-file", "-e", sha],
                cwd=cwd,
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

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
            "gh_test_lines_per_kloc": 0.0,
            "gh_test_cases_per_kloc": 0.0,
            "gh_asserts_case_per_kloc": 0.0,
        }

        # Counters for absolute values
        total_sloc = 0
        total_test_lines = 0
        total_test_cases = 0
        total_asserts = 0

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
                            total_test_lines += line_count
                            total_test_cases += self._count_tests(content, language)
                            total_asserts += self._count_asserts(content, language)
                        elif _is_source_file(rel_path):
                            total_sloc += line_count

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

        # Calculate per-KLOC metrics
        stats["gh_sloc"] = total_sloc

        if total_sloc > 0:
            kloc = total_sloc / 1000.0
            stats["gh_test_lines_per_kloc"] = total_test_lines / kloc
            stats["gh_test_cases_per_kloc"] = total_test_cases / kloc
            stats["gh_asserts_case_per_kloc"] = total_asserts / kloc
        else:
            stats["gh_test_lines_per_kloc"] = 0.0
            stats["gh_test_cases_per_kloc"] = 0.0
            stats["gh_asserts_case_per_kloc"] = 0.0

        return stats

    def _count_tests(self, content: str, language: str | None) -> int:
        count = 0
        lang = (language or "").lower()
        for line in content.splitlines():
            clean_line = _strip_comments(line, lang)
            if _matches_test_definition(clean_line, lang):
                count += 1
        return count

    def _count_asserts(self, content: str, language: str | None) -> int:
        count = 0
        lang = (language or "").lower()
        for line in content.splitlines():
            clean_line = _strip_comments(line, lang)
            if _matches_assertion(clean_line, lang):
                count += 1
        return count

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "gh_repo_age": 0.0,
            "gh_repo_num_commits": 0,
            "gh_sloc": 0,
            "gh_test_lines_per_kloc": 0.0,
            "gh_test_cases_per_kloc": 0.0,
            "gh_asserts_case_per_kloc": 0.0,
            "gh_project_name": None,
            "gh_is_pr": None,
            "gh_pr_created_at": None,
            "gh_pull_req_num": None,
            "gh_lang": None,
            "git_branch": None,
            "git_trigger_commit": None,
            "ci_provider": None,
            "gh_build_started_at": None,
        }
