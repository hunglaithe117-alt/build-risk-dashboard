"""
Repository Snapshot Feature Node.

Extracts point-in-time repository metrics:
- Age and commit count
- SLOC metrics
- Test density
- Build metadata
"""

import logging
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle
from app.pipeline.resources.git_repo import GitRepoHandle
from app.services.extracts.languages.registry import LanguageRegistry
from app.utils.locking import repo_lock

logger = logging.getLogger(__name__)


@register_feature(
    name="repo_snapshot_features",
    requires_resources={ResourceNames.GIT_REPO, ResourceNames.WORKFLOW_RUN},
    provides={
        "gh_repo_age",
        "gh_repo_num_commits",
        "gh_sloc",
        "gh_test_lines_per_kloc",
        "gh_test_cases_per_kloc",
        "gh_asserts_case_per_kloc",
        # Metadata
        "gh_project_name",
        "gh_is_pr",
        "gh_pr_created_at",
        "gh_pull_req_num",
        "gh_lang",
        "git_branch",
        "git_trigger_commit",
        "ci_provider",
        "gh_build_started_at",
    },
    group="repo",
)
class RepoSnapshotNode(FeatureNode):
    """
    Captures repository state at the build's commit.

    Uses git worktree to checkout the specific commit without
    affecting the main repository.
    """

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        git_handle: GitRepoHandle = context.get_resource(ResourceNames.GIT_REPO)
        workflow_run = context.workflow_run
        repo = context.repo

        # Extract metadata from workflow run
        payload = workflow_run.raw_payload if workflow_run else {}
        head_branch = payload.get("head_branch")
        pull_requests = payload.get("pull_requests", [])
        is_pr = len(pull_requests) > 0 or payload.get("event") == "pull_request"

        pr_number = None
        pr_created_at = None
        if pull_requests:
            pr_data = pull_requests[0]
            pr_number = pr_data.get("number")
            pr_created_at = pr_data.get("created_at")

        if not git_handle.is_commit_available:
            return self._metadata_only(
                repo, workflow_run, head_branch, is_pr, pr_number, pr_created_at
            )

        effective_sha = git_handle.effective_sha
        repo_path = git_handle.path

        # History metrics
        age, num_commits = self._get_history_metrics(repo_path, effective_sha)

        # Snapshot metrics (SLOC, tests)
        languages = []
        if repo.source_languages:
            for lang in repo.source_languages:
                val = (
                    lang.value.lower() if hasattr(lang, "value") else str(lang).lower()
                )
                languages.append(val)

        with repo_lock(str(repo.id)):
            snapshot_metrics = self._analyze_snapshot(
                repo_path, effective_sha, languages
            )

        return {
            "gh_repo_age": age,
            "gh_repo_num_commits": num_commits,
            **snapshot_metrics,
            # Metadata
            "gh_project_name": repo.full_name,
            "gh_is_pr": is_pr,
            "gh_pr_created_at": pr_created_at,
            "gh_pull_req_num": pr_number,
            "gh_lang": repo.main_lang,
            "git_branch": head_branch,
            "git_trigger_commit": workflow_run.head_sha if workflow_run else None,
            "ci_provider": repo.ci_provider,
            "gh_build_started_at": workflow_run.created_at if workflow_run else None,
        }

    def _get_history_metrics(self, repo_path: Path, sha: str) -> Tuple[float, int]:
        """Calculate repository age and total commits."""
        try:
            # First commit timestamp
            first_commit_ts = (
                subprocess.run(
                    ["git", "log", "--reverse", "--format=%ct", sha],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True,
                    check=True,
                )
                .stdout.strip()
                .split("\n")[0]
            )

            first_commit_date = datetime.fromtimestamp(
                int(first_commit_ts), tz=timezone.utc
            )
            age_days = (datetime.now(timezone.utc) - first_commit_date).days

            # Commit count
            commit_count = subprocess.run(
                ["git", "rev-list", "--count", sha],
                cwd=str(repo_path),
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()

            return float(age_days), int(commit_count)
        except Exception as e:
            logger.warning(f"Failed to get history metrics: {e}")
            return 0.0, 0

    def _analyze_snapshot(
        self, repo_path: Path, sha: str, languages: list[str]
    ) -> Dict[str, Any]:
        """Analyze code at specific commit using worktree."""
        metrics = {
            "gh_sloc": 0,
            "gh_test_lines_per_kloc": 0.0,
            "gh_test_cases_per_kloc": 0.0,
            "gh_asserts_case_per_kloc": 0.0,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            worktree_path = Path(tmpdir) / "snapshot"

            try:
                # Create worktree
                subprocess.run(
                    ["git", "worktree", "add", "--detach", str(worktree_path), sha],
                    cwd=str(repo_path),
                    capture_output=True,
                    check=True,
                )

                # Analyze files
                src_lines = 0
                test_lines = 0
                test_cases = 0
                asserts = 0

                for path in worktree_path.rglob("*"):
                    if not path.is_file():
                        continue

                    rel_path = str(path.relative_to(worktree_path))

                    # Skip hidden and vendor directories
                    if any(part.startswith(".") for part in rel_path.split("/")):
                        continue
                    if any(
                        x in rel_path for x in ["vendor/", "node_modules/", "venv/"]
                    ):
                        continue

                    try:
                        content = path.read_text(errors="ignore")
                        lines = content.splitlines()
                        line_count = len(lines)

                        # Check against all selected languages
                        matched_lang = None
                        matched_strategy = None
                        is_test = False

                        # If no languages selected, try generic check (pass None -> generic)
                        langs_to_check = languages if languages else [None]

                        # First pass: Check if it's a test file in any language
                        for lang_name in langs_to_check:
                            strategy = LanguageRegistry.get_strategy(lang_name or "")
                            if strategy.is_test_file(rel_path):
                                is_test = True
                                matched_lang = lang_name
                                matched_strategy = strategy
                                break

                        if is_test and matched_strategy:
                            test_lines += line_count
                            # Count test cases and assertions using the matched strategy
                            for line in lines:
                                clean_line = matched_strategy.strip_comments(line)
                                if matched_strategy.matches_test_definition(clean_line):
                                    test_cases += 1
                                if matched_strategy.matches_assertion(clean_line):
                                    asserts += 1
                        else:
                            # Second pass: Check if it's a source file in any language
                            is_source = False
                            for lang_name in langs_to_check:
                                strategy = LanguageRegistry.get_strategy(
                                    lang_name or ""
                                )
                                if strategy.is_source_file(rel_path):
                                    is_source = True
                                    break

                            if is_source:
                                src_lines += line_count
                    except Exception:
                        continue

                metrics["gh_sloc"] = src_lines

                # Calculate per-KLOC metrics
                if src_lines > 0:
                    kloc = src_lines / 1000.0
                    metrics["gh_test_lines_per_kloc"] = test_lines / kloc
                    metrics["gh_test_cases_per_kloc"] = test_cases / kloc
                    metrics["gh_asserts_case_per_kloc"] = asserts / kloc

            except Exception as e:
                logger.error(f"Failed to analyze snapshot: {e}")
            finally:
                # Clean up worktree
                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(worktree_path)],
                        cwd=str(repo_path),
                        capture_output=True,
                    )
                except Exception:
                    pass

        return metrics

    def _metadata_only(
        self, repo, workflow_run, head_branch, is_pr, pr_number, pr_created_at
    ) -> Dict[str, Any]:
        """Return only metadata when commit is not available."""
        return {
            "gh_repo_age": None,
            "gh_repo_num_commits": None,
            "gh_sloc": None,
            "gh_test_lines_per_kloc": None,
            "gh_test_cases_per_kloc": None,
            "gh_asserts_case_per_kloc": None,
            "gh_project_name": repo.full_name,
            "gh_is_pr": is_pr,
            "gh_pr_created_at": pr_created_at,
            "gh_pull_req_num": pr_number,
            "gh_lang": repo.main_lang,
            "git_branch": head_branch,
            "git_trigger_commit": workflow_run.head_sha if workflow_run else None,
            "ci_provider": repo.ci_provider,
            "gh_build_started_at": workflow_run.created_at if workflow_run else None,
        }
