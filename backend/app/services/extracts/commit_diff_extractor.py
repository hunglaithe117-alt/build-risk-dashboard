import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from app.models.entities.build_sample import BuildSample
from app.models.entities.imported_repository import ImportedRepository
from app.services.extracts.diff_analyzer import (
    _count_test_cases,
    _is_doc_file,
    _is_source_file,
    _is_test_file,
)
from app.services.github.github_app import get_installation_token
from app.utils.locking import repo_lock
from pymongo.database import Database

logger = logging.getLogger(__name__)

REPOS_DIR = Path("repos")
REPOS_DIR.mkdir(exist_ok=True)


class CommitDiffExtractor:
    def __init__(self, db: Database):
        self.db = db

    def extract(
        self, build_sample: BuildSample, repo: ImportedRepository
    ) -> Dict[str, Any]:
        commit_sha = build_sample.tr_original_commit
        if not commit_sha:
            logger.warning(f"No commit SHA for build {build_sample.id}")
            return self._empty_result()

        repo_path = REPOS_DIR / str(repo.id)

        try:
            with repo_lock(str(repo.id)):
                self._ensure_repo(repo, repo_path)

                # Fetch to ensure we have the commit
                self._run_git(repo_path, ["fetch", "origin"])

            # Check if commit exists
            if not self._commit_exists(repo_path, commit_sha):
                logger.warning(f"Commit {commit_sha} not found in {repo.full_name}")
                return self._empty_result()

            # Get parent commit
            parent_sha = self._get_parent_commit(repo_path, commit_sha)
            if not parent_sha:
                logger.info(f"No parent for {commit_sha}, treating as initial commit")
                return self._empty_result()

            # Get diff stats
            return self._analyze_diff(repo_path, parent_sha, commit_sha, repo.main_lang)

        except Exception as e:
            logger.error(f"Failed to extract diff features for {repo.full_name}: {e}")
            return self._empty_result()

    def _ensure_repo(self, repo: ImportedRepository, repo_path: Path):
        if repo_path.exists():
            # Validate it's a git repo
            if (repo_path / ".git").exists():
                return
            else:
                shutil.rmtree(repo_path)

        # Clone
        token = get_installation_token(repo.installation_id, self.db)
        auth_url = f"https://x-access-token:{token}@github.com/{repo.full_name}.git"

        logger.info(f"Cloning {repo.full_name} to {repo_path}")
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

    def _get_parent_commit(self, cwd: Path, sha: str) -> str | None:
        try:
            return self._run_git(cwd, ["rev-parse", f"{sha}^"])
        except subprocess.CalledProcessError:
            return None

    def _analyze_diff(
        self, cwd: Path, parent: str, current: str, language: str | None
    ) -> Dict[str, Any]:
        stats = {
            "git_diff_src_churn": 0,
            "git_diff_test_churn": 0,
            "gh_diff_files_added": 0,
            "gh_diff_files_deleted": 0,
            "gh_diff_files_modified": 0,
            "gh_diff_tests_added": 0,
            "gh_diff_tests_deleted": 0,
            "gh_diff_src_files": 0,
            "gh_diff_doc_files": 0,
            "gh_diff_other_files": 0,
        }

        # Get name-status to count files
        # git diff --name-status parent current
        name_status_out = self._run_git(cwd, ["diff", "--name-status", parent, current])

        for line in name_status_out.splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            status_code = parts[0][0]
            path = parts[-1]  # Handle renames if needed, but usually last is dest

            if status_code == "A":
                stats["gh_diff_files_added"] += 1
            elif status_code == "D":
                stats["gh_diff_files_deleted"] += 1
            elif status_code == "M":
                stats["gh_diff_files_modified"] += 1

            if _is_doc_file(path):
                stats["gh_diff_doc_files"] += 1
            elif _is_source_file(path):
                stats["gh_diff_src_files"] += 1
            elif not _is_test_file(path):
                stats["gh_diff_other_files"] += 1

        # Get numstat for churn
        # git diff --numstat parent current
        numstat_out = self._run_git(cwd, ["diff", "--numstat", parent, current])

        for line in numstat_out.splitlines():
            parts = line.split("\t")
            if len(parts) < 3:
                continue
            try:
                added = int(parts[0]) if parts[0] != "-" else 0
                deleted = int(parts[1]) if parts[1] != "-" else 0
            except ValueError:
                continue
            path = parts[2]

            if _is_source_file(path):
                stats["git_diff_src_churn"] += added + deleted
            elif _is_test_file(path):
                stats["git_diff_test_churn"] += added + deleted

        # Get patch for test cases
        # This might be heavy for large diffs
        patch_out = self._run_git(cwd, ["diff", parent, current])
        added_tests, deleted_tests = _count_test_cases(patch_out, language)
        stats["gh_diff_tests_added"] = added_tests
        stats["gh_diff_tests_deleted"] = deleted_tests

        return stats

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "git_diff_src_churn": 0,
            "git_diff_test_churn": 0,
            "gh_diff_files_added": 0,
            "gh_diff_files_deleted": 0,
            "gh_diff_files_modified": 0,
            "gh_diff_tests_added": 0,
            "gh_diff_tests_deleted": 0,
            "gh_diff_src_files": 0,
            "gh_diff_doc_files": 0,
            "gh_diff_other_files": 0,
        }
