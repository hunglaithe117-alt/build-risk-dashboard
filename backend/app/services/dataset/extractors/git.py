"""
Git Feature Extractor.

Extracts features that require access to the git repository.
Matches implementation in extracts/git_feature_extractor.py and extracts/repo_snapshot_extractor.py.
"""

import logging
import re
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from git import Repo, Commit

from app.services.dataset.context import DatasetExtractionContext
from app.services.dataset.extractors.base import BaseFeatureExtractor
from app.services.extracts.diff_analyzer import (
    _count_test_cases,
    _is_doc_file,
    _is_source_file,
    _is_test_file,
    _matches_test_definition,
    _matches_assertion,
    _strip_comments,
)
from app.services.commit_replay import ensure_commit_exists
from app.services.github.github_app import get_installation_token
from app.repositories.workflow_run import WorkflowRunRepository

logger = logging.getLogger(__name__)


class GitFeatureExtractor(BaseFeatureExtractor):
    """
    Extractor for features that require git repository access.
    
    Includes diff analysis, snapshot metrics, and team statistics.
    Matches the implementation in extracts/git_feature_extractor.py and extracts/repo_snapshot_extractor.py.
    """
    
    SUPPORTED_FEATURES = {
        # Build stats features (from git_feature_extractor.py)
        "git_prev_commit_resolution_status",
        "git_prev_built_commit",
        "tr_prev_build",
        "git_all_built_commits",
        "git_num_all_built_commits",
        # Diff features
        "git_diff_src_churn",
        "git_diff_test_churn",
        "gh_diff_files_added",
        "gh_diff_files_deleted",
        "gh_diff_files_modified",
        "gh_diff_tests_added",
        "gh_diff_tests_deleted",
        "gh_diff_src_files",
        "gh_diff_doc_files",
        "gh_diff_other_files",
        # Snapshot features (from repo_snapshot_extractor.py)
        "gh_repo_age",
        "gh_repo_num_commits",
        "gh_sloc",
        "gh_test_lines_per_kloc",
        "gh_test_cases_per_kloc",
        "gh_asserts_case_per_kloc",
        # Team features
        "gh_team_size",
        "gh_by_core_team_member",
        "gh_num_commits_on_files_touched",
        # Metadata features (from repo_snapshot_extractor.py)
        "gh_project_name",
        "gh_is_pr",
        "gh_pr_created_at",
        "gh_pull_req_num",
        "gh_lang",
        "git_branch",
        "git_trigger_commit",
        "ci_provider",
        "gh_build_started_at",
    }
    
    BUILD_STATS_FEATURES = {
        "git_prev_commit_resolution_status",
        "git_prev_built_commit",
        "tr_prev_build",
        "git_all_built_commits",
        "git_num_all_built_commits",
    }
    
    DIFF_FEATURES = {
        "git_diff_src_churn", "git_diff_test_churn",
        "gh_diff_files_added", "gh_diff_files_deleted", "gh_diff_files_modified",
        "gh_diff_tests_added", "gh_diff_tests_deleted",
        "gh_diff_src_files", "gh_diff_doc_files", "gh_diff_other_files",
    }
    
    SNAPSHOT_FEATURES = {
        "gh_repo_age", "gh_repo_num_commits", "gh_sloc",
        "gh_test_lines_per_kloc", "gh_test_cases_per_kloc", "gh_asserts_case_per_kloc",
    }
    
    TEAM_FEATURES = {
        "gh_team_size", "gh_by_core_team_member",
        "gh_num_commits_on_files_touched",
    }
    
    METADATA_FEATURES = {
        "gh_project_name", "gh_is_pr", "gh_pr_created_at", "gh_pull_req_num",
        "gh_lang", "git_branch", "git_trigger_commit", "ci_provider", "gh_build_started_at",
    }
    
    def __init__(self, repos_dir: Path):
        """
        Initialize git extractor.
        
        Args:
            repos_dir: Directory where repositories are cloned
        """
        self.repos_dir = repos_dir
        self.workflow_run_repo: Optional[WorkflowRunRepository] = None
    
    def _get_token(self, ctx: DatasetExtractionContext) -> Optional[str]:
        """Get GitHub token for repo access."""
        if ctx.repo.installation_id:
            return get_installation_token(ctx.repo.installation_id, ctx.db)
        else:
            from app.config import settings
            tokens = settings.GITHUB_TOKENS
            if tokens and tokens[0]:
                return tokens[0]
        return None
    
    def _ensure_repo(self, ctx: DatasetExtractionContext, repo_path: Path) -> bool:
        """
        Clone repository if not exists.
        
        Args:
            ctx: Extraction context
            repo_path: Path where repo should be cloned
            
        Returns:
            True if repo exists or was cloned successfully
        """
        import shutil
        
        if repo_path.exists():
            if (repo_path / ".git").exists():
                return True
            else:
                shutil.rmtree(repo_path)
        
        auth_url = f"https://github.com/{ctx.repo.full_name}.git"
        token = self._get_token(ctx)
        
        if token:
            if ctx.repo.installation_id:
                auth_url = f"https://x-access-token:{token}@github.com/{ctx.repo.full_name}.git"
            else:
                auth_url = f"https://{token}@github.com/{ctx.repo.full_name}.git"
        
        try:
            logger.info(f"Cloning {ctx.repo.full_name} to {repo_path}")
            repo_path.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "clone", "--depth", "1000", auth_url, str(repo_path)],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to clone {ctx.repo.full_name}: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Failed to clone {ctx.repo.full_name}: {e}")
            return False
    
    def extract(self, ctx: DatasetExtractionContext, features: Set[str]) -> None:
        """Extract features that require git repository."""
        from app.utils.locking import repo_lock
        
        repo_path = self.repos_dir / str(ctx.repo.id)
        
        # Clone repository if not exists
        if not repo_path.exists():
            cloned = self._ensure_repo(ctx, repo_path)
            if not cloned:
                ctx.add_warning(f"Repository not cloned and could not be cloned: {ctx.repo.full_name}")
                return
        
        # Get language for file detection
        language = None
        if ctx.source_languages:
            language = ctx.source_languages[0].lower()
        
        # Initialize workflow_run_repo for build stats
        self.workflow_run_repo = WorkflowRunRepository(ctx.db)
        
        try:
            with repo_lock(str(ctx.repo.id)):
                # Ensure repo is fetched
                self._run_git(repo_path, ["fetch", "origin"])
                
                # Ensure commit exists (handle forks)
                token = self._get_token(ctx)
                effective_sha = ensure_commit_exists(
                    repo_path, ctx.commit_sha, ctx.repo.full_name, token
                )
                
                if not effective_sha:
                    ctx.add_warning(f"Commit {ctx.commit_sha} not found in {ctx.repo.full_name}")
                    return
                
                git_repo = Repo(str(repo_path))
                
                # 1. Extract build stats (needed for diff and team features)
                built_commits = []
                prev_built_commit = None
                
                if features & self.BUILD_STATS_FEATURES or features & self.DIFF_FEATURES or features & self.TEAM_FEATURES:
                    build_stats = self._calculate_build_stats(
                        ctx, git_repo, effective_sha
                    )
                    
                    for name, value in build_stats.items():
                        if name in features:
                            ctx.add_feature(name, value)
                    
                    # Store for other extractors
                    built_commits = build_stats.get("git_all_built_commits", [])
                    prev_built_commit = build_stats.get("git_prev_built_commit")
                    ctx.git_all_built_commits = built_commits
                    ctx.tr_prev_build = build_stats.get("tr_prev_build")
                
                # 2. Extract diff features (uses built_commits)
                if features & self.DIFF_FEATURES:
                    diff_stats = self._calculate_diff_features(
                        repo_path, built_commits, prev_built_commit, effective_sha, language
                    )
                    for name, value in diff_stats.items():
                        if name in features:
                            ctx.add_feature(name, value)
                
                # 3. Extract snapshot features
                if features & self.SNAPSHOT_FEATURES:
                    snapshot_stats = self._calculate_snapshot_features(
                        repo_path, effective_sha, language
                    )
                    for name, value in snapshot_stats.items():
                        if name in features:
                            ctx.add_feature(name, value)
                
                # 4. Extract team features (uses built_commits)
                if features & self.TEAM_FEATURES:
                    team_stats = self._calculate_team_features(
                        ctx, git_repo, built_commits, effective_sha
                    )
                    for name, value in team_stats.items():
                        if name in features:
                            ctx.add_feature(name, value)
                
                # 5. Extract metadata features
                if features & self.METADATA_FEATURES:
                    metadata = self._extract_metadata_features(ctx)
                    for name, value in metadata.items():
                        if name in features:
                            ctx.add_feature(name, value)
                        
        except Exception as e:
            ctx.add_error(f"Git feature extraction failed: {e}")
            logger.error(f"Git extraction error: {e}")
    
    def _extract_metadata_features(self, ctx: DatasetExtractionContext) -> Dict[str, Any]:
        """Extract metadata features from workflow run."""
        payload = ctx.workflow_run.raw_payload or {}
        head_branch = payload.get("head_branch")
        pull_requests = payload.get("pull_requests", [])
        is_pr = len(pull_requests) > 0 or payload.get("event") == "pull_request"
        
        pr_number = None
        pr_created_at = None
        if pull_requests:
            pr_data = pull_requests[0]
            pr_number = pr_data.get("number")
            pr_created_at = pr_data.get("created_at")
        
        return {
            "gh_project_name": ctx.repo.full_name,
            "gh_is_pr": is_pr,
            "gh_pr_created_at": pr_created_at,
            "gh_pull_req_num": pr_number,
            "gh_lang": ctx.repo.main_lang,
            "git_branch": head_branch,
            "git_trigger_commit": ctx.workflow_run.head_sha,
            "ci_provider": (
                ctx.repo.ci_provider.value
                if hasattr(ctx.repo.ci_provider, "value")
                else ctx.repo.ci_provider
            ),
            "gh_build_started_at": ctx.workflow_run.created_at,
        }
    
    def _calculate_build_stats(
        self, 
        ctx: DatasetExtractionContext, 
        git_repo: Repo, 
        commit_sha: str
    ) -> Dict[str, Any]:
        """
        Calculate build stats - find previous build and commits since then.
        Matches logic in extracts/git_feature_extractor.py._calculate_build_stats()
        """
        try:
            build_commit = git_repo.commit(commit_sha)
        except Exception:
            return {}
        
        prev_commits_objs: List[Commit] = [build_commit]
        status = "no_previous_build"
        last_commit = None
        prev_build_id = None
        
        # Walk commit history to find previous build
        walker = git_repo.iter_commits(commit_sha, max_count=1000)
        first = True
        
        for commit in walker:
            if first:
                if len(commit.parents) > 1:
                    status = "merge_found"
                    break
                first = False
                continue
            
            last_commit = commit
            
            # Check if this commit triggered a build
            existing_build = self.workflow_run_repo.find_one({
                "repo_id": ctx.repo.id,
                "head_sha": commit.hexsha,
                "status": "completed",
                "workflow_run_id": {"$ne": ctx.workflow_run.workflow_run_id},
            })
            
            if existing_build:
                status = "build_found"
                prev_build_id = existing_build.run_number
                break
            
            prev_commits_objs.append(commit)
            
            if len(commit.parents) > 1:
                status = "merge_found"
                break
        
        commits_hex = [c.hexsha for c in prev_commits_objs]
        
        return {
            "git_prev_commit_resolution_status": status,
            "git_prev_built_commit": last_commit.hexsha if last_commit else None,
            "tr_prev_build": prev_build_id,
            "git_all_built_commits": commits_hex,
            "git_num_all_built_commits": len(commits_hex),
        }
    
    def _run_git(self, cwd: Path, args: List[str]) -> str:
        """Run a git command and return stdout."""
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()
    
    def _get_parent_commit(self, cwd: Path, sha: str) -> str | None:
        """Get parent commit SHA."""
        try:
            return self._run_git(cwd, ["rev-parse", f"{sha}^"])
        except subprocess.CalledProcessError:
            return None
    
    def _calculate_diff_features(
        self,
        repo_path: Path,
        built_commits: List[str],
        prev_built_commit: str | None,
        current_commit: str,
        language: str | None,
    ) -> Dict[str, Any]:
        """
        Calculate diff-based features.
        Matches implementation in extracts/git_feature_extractor.py._calculate_diff_features()
        """
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
        
        # 1. Cumulative Churn & File Counts (Iterate over all built commits)
        for sha in built_commits:
            parent = self._get_parent_commit(repo_path, sha)
            if not parent:
                continue
            
            # git diff --name-status parent sha
            try:
                name_status_out = self._run_git(
                    repo_path, ["diff", "--name-status", parent, sha]
                )
            except Exception:
                continue
            
            for line in name_status_out.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                status_code = parts[0][0]
                path = parts[-1]
                
                if status_code == "A":
                    stats["gh_diff_files_added"] += 1
                elif status_code == "D":
                    stats["gh_diff_files_deleted"] += 1
                elif status_code == "M":
                    stats["gh_diff_files_modified"] += 1
                
                if _is_doc_file(path):
                    stats["gh_diff_doc_files"] += 1
                elif _is_source_file(path) or _is_test_file(path):
                    # TravisTorrent maps both src and test to :programming (src_files)
                    stats["gh_diff_src_files"] += 1
                else:
                    stats["gh_diff_other_files"] += 1
            
            # git diff --numstat parent sha
            try:
                numstat_out = self._run_git(repo_path, ["diff", "--numstat", parent, sha])
            except Exception:
                continue
            
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
        
        # 2. Net Test Case Diff (Compare prev_built_commit vs current_commit)
        if prev_built_commit:
            try:
                patch_out = self._run_git(
                    repo_path, ["diff", prev_built_commit, current_commit]
                )
                added_tests, deleted_tests = _count_test_cases(patch_out, language)
                stats["gh_diff_tests_added"] = added_tests
                stats["gh_diff_tests_deleted"] = deleted_tests
            except Exception:
                pass
        
        return stats
    
    def _calculate_snapshot_features(
        self, 
        repo_path: Path,
        commit_sha: str,
        language: str | None,
    ) -> Dict[str, Any]:
        """
        Calculate snapshot features at commit time.
        Matches implementation in extracts/repo_snapshot_extractor.py.
        """
        stats = {
            "gh_repo_age": 0.0,
            "gh_repo_num_commits": 0,
            "gh_sloc": 0,
            "gh_test_lines_per_kloc": 0.0,
            "gh_test_cases_per_kloc": 0.0,
            "gh_asserts_case_per_kloc": 0.0,
        }
        
        # Num commits
        try:
            count_out = self._run_git(repo_path, ["rev-list", "--count", commit_sha])
            stats["gh_repo_num_commits"] = int(count_out)
        except Exception:
            pass
        
        # Age
        try:
            current_ts = self._run_git(repo_path, ["show", "-s", "--format=%ct", commit_sha])
            roots = self._run_git(
                repo_path, ["rev-list", "--max-parents=0", commit_sha]
            ).splitlines()
            if roots:
                root_sha = roots[-1]
                first_ts = self._run_git(repo_path, ["show", "-s", "--format=%ct", root_sha])
                age_seconds = int(current_ts) - int(first_ts)
                stats["gh_repo_age"] = max(0.0, age_seconds / 86400.0)
        except Exception:
            pass
        
        # SLOC metrics using worktree
        total_sloc = 0
        total_test_lines = 0
        total_test_cases = 0
        total_asserts = 0
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            worktree_path = Path(tmp_dir) / "worktree"
            try:
                subprocess.run(
                    ["git", "worktree", "add", "-f", str(worktree_path), commit_sha],
                    cwd=repo_path,
                    check=True,
                    capture_output=True,
                )
                
                for file_path in worktree_path.rglob("*"):
                    if not file_path.is_file():
                        continue
                    if ".git" in file_path.parts:
                        continue
                    
                    rel_path = str(file_path.relative_to(worktree_path))
                    
                    try:
                        with open(file_path, "r", errors="ignore") as f:
                            lines = f.readlines()
                            line_count = len(lines)
                            content = "".join(lines)
                        
                        lang = (language or "").lower()
                        if _is_test_file(rel_path):
                            total_test_lines += line_count
                            total_test_cases += self._count_tests(content, lang)
                            total_asserts += self._count_asserts(content, lang)
                        elif _is_source_file(rel_path):
                            total_sloc += line_count
                    except Exception:
                        pass
                
            finally:
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "-f", str(worktree_path)],
                        cwd=repo_path,
                        capture_output=True,
                    )
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        cwd=repo_path,
                        capture_output=True,
                    )
                except Exception:
                    pass
        
        stats["gh_sloc"] = total_sloc
        
        if total_sloc > 0:
            kloc = total_sloc / 1000.0
            stats["gh_test_lines_per_kloc"] = total_test_lines / kloc
            stats["gh_test_cases_per_kloc"] = total_test_cases / kloc
            stats["gh_asserts_case_per_kloc"] = total_asserts / kloc
        
        return stats
    
    def _count_tests(self, content: str, language: str | None) -> int:
        """Count test definitions in file content."""
        count = 0
        lang = (language or "").lower()
        for line in content.splitlines():
            clean_line = _strip_comments(line, lang)
            if _matches_test_definition(clean_line, lang):
                count += 1
        return count
    
    def _count_asserts(self, content: str, language: str | None) -> int:
        """Count assertions in file content."""
        count = 0
        lang = (language or "").lower()
        for line in content.splitlines():
            clean_line = _strip_comments(line, lang)
            if _matches_assertion(clean_line, lang):
                count += 1
        return count
    
    def _calculate_team_features(
        self,
        ctx: DatasetExtractionContext,
        git_repo: Repo,
        built_commits: List[str],
        commit_sha: str,
        chunk_size: int = 50,
    ) -> Dict[str, Any]:
        """
        Calculate team-related features.
        Matches implementation in extracts/git_feature_extractor.py._calculate_team_stats()
        """
        if not built_commits:
            return {}
        
        ref_date = ctx.gh_build_started_at
        if not ref_date:
            try:
                trigger_commit = git_repo.commit(built_commits[0])
                ref_date = datetime.fromtimestamp(trigger_commit.committed_date, tz=timezone.utc)
            except Exception:
                return {}
        
        start_date = ref_date - timedelta(days=90)
        
        # Committer Team: Direct pushers (excluding PR merges, squash, rebase)
        committer_names = self._get_direct_committers(
            Path(git_repo.working_dir), start_date, ref_date
        )
        
        # Merger Team: People who merged PRs OR triggered workflow runs (PR/Push)
        merger_logins = self._get_pr_mergers(ctx.repo.id, start_date, ref_date)
        
        core_team = committer_names | merger_logins
        gh_team_size = len(core_team)
        
        # Check if the build trigger author is in the core team
        is_core_member = False
        try:
            trigger_commit = git_repo.commit(commit_sha)
            author_name = trigger_commit.author.name
            committer_name = trigger_commit.committer.name
            
            if author_name in core_team or committer_name in core_team:
                is_core_member = True
        except Exception:
            pass
        
        # Files Touched
        files_touched: Set[str] = set()
        for sha in built_commits:
            try:
                commit = git_repo.commit(sha)
                if commit.parents:
                    diffs = commit.diff(commit.parents[0])
                    for d in diffs:
                        if d.b_path:
                            files_touched.add(d.b_path)
                        if d.a_path:
                            files_touched.add(d.a_path)
            except Exception:
                pass
        
        num_commits_on_files = 0
        if files_touched:
            try:
                all_shas = set()
                paths = list(files_touched)
                trigger_sha = built_commits[0]
                
                for i in range(0, len(paths), chunk_size):
                    chunk = paths[i : i + chunk_size]
                    commits_on_files = git_repo.git.log(
                        trigger_sha,
                        "--since",
                        start_date.isoformat(),
                        "--format=%H",
                        "--",
                        *chunk,
                    ).splitlines()
                    all_shas.update(set(commits_on_files))
                
                for sha in built_commits:
                    if sha in all_shas:
                        all_shas.remove(sha)
                
                num_commits_on_files = len(all_shas)
            except Exception as e:
                logger.warning(f"Failed to count commits on files: {e}")
        
        return {
            "gh_team_size": gh_team_size,
            "gh_by_core_team_member": is_core_member,
            "gh_num_commits_on_files_touched": num_commits_on_files,
        }
    
    def _get_direct_committers(
        self, repo_path: Path, start_date: datetime, end_date: datetime
    ) -> Set[str]:
        """
        Get NAMES of users who pushed directly to the main branch (not via PR).
        Matches implementation in extracts/git_feature_extractor.py.
        """
        pr_pattern = re.compile(r"\s\(#\d+\)")
        
        try:
            output = self._run_git(
                repo_path,
                [
                    "log",
                    "--first-parent",
                    "--no-merges",
                    f"--since={start_date.isoformat()}",
                    f"--until={end_date.isoformat()}",
                    "--format=%H|%an|%s",
                ],
            )
        except subprocess.CalledProcessError:
            return set()
        
        direct_committers = set()
        for line in output.splitlines():
            if not line.strip():
                continue
            
            parts = line.split("|", 2)
            if len(parts) < 3:
                continue
            
            name = parts[1]
            message = parts[2]
            
            # Filter out Squash/Rebase PRs
            if pr_pattern.search(message):
                continue
            
            # Filter out standard GitHub merge messages
            if "Merge pull request" in message:
                continue
            
            direct_committers.add(name)
        
        return direct_committers
    
    def _get_pr_mergers(
        self, repo_id, start_date: datetime, end_date: datetime
    ) -> Set[str]:
        """
        Get logins of users who triggered PR workflow runs in the given time window.
        """
        mergers = set()
        
        try:
            runs = self.workflow_run_repo.find_in_date_range(
                repo_id, start_date, end_date
            )
            for run in runs:
                payload = run.raw_payload
                pull_requests = payload.get("pull_requests", [])
                is_pr = len(pull_requests) > 0 or payload.get("event") == "pull_request"
                
                if is_pr:
                    actor = payload.get("triggering_actor", {})
                    login = actor.get("login")
                    if login:
                        mergers.add(login)
        except Exception as e:
            logger.warning(f"Failed to get workflow run actors: {e}")
        
        return mergers