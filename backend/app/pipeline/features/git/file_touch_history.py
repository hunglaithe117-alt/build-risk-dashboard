"""
File Touch History Node.

Extracts file-level history metrics:
- gh_num_commits_on_files_touched: Total commits on files modified by this build
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Set

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle

logger = logging.getLogger(__name__)


@register_feature(
    name="file_touch_history",
    requires_resources={ResourceNames.GIT_REPO},
    requires_features={"git_all_built_commits"},
    provides={
        "gh_num_commits_on_files_touched",
    },
    group="git",
    priority=3,  # Lower priority - expensive operation
)
class FileTouchHistoryNode(FeatureNode):
    """
    Calculates how many historical commits touched the same files as this build.
    """

    LOOKBACK_DAYS = 90
    CHUNK_SIZE = 50

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        git_handle: GitRepoHandle = context.get_resource(ResourceNames.GIT_REPO)

        if not git_handle.is_commit_available:
            return {"gh_num_commits_on_files_touched": 0}

        repo = git_handle.repo
        effective_sha = git_handle.effective_sha
        built_commits = context.get_feature("git_all_built_commits", [])
        build_sample = context.build_sample

        if not built_commits:
            return {"gh_num_commits_on_files_touched": 0}

        # Get reference date
        ref_date = getattr(build_sample, "created_at", None) or getattr(
            build_sample, "gh_build_started_at", None
        )
        if not ref_date:
            try:
                current_commit = repo.commit(effective_sha)
                ref_date = datetime.fromtimestamp(
                    current_commit.committed_date, tz=timezone.utc
                )
            except Exception:
                return {"gh_num_commits_on_files_touched": 0}

        if ref_date.tzinfo is None:
            ref_date = ref_date.replace(tzinfo=timezone.utc)

        start_date = ref_date - timedelta(days=self.LOOKBACK_DAYS)

        num_commits = self._calculate_file_history(
            repo, built_commits, effective_sha, start_date
        )

        return {"gh_num_commits_on_files_touched": num_commits}

    def _calculate_file_history(
        self, repo, built_commits: List[str], head_sha: str, start_date: datetime
    ) -> int:
        """Calculate number of commits touching files modified in this build."""
        # Collect files touched by this build
        files_touched: Set[str] = set()
        for sha in built_commits:
            try:
                commit = repo.commit(sha)
                if commit.parents:
                    diffs = commit.diff(commit.parents[0])
                    for d in diffs:
                        if d.b_path:
                            files_touched.add(d.b_path)
                        if d.a_path:
                            files_touched.add(d.a_path)
            except Exception:
                pass

        if not files_touched:
            return 0

        # Count commits on these files in chunks
        all_shas: Set[str] = set()
        paths = list(files_touched)
        start_iso = start_date.isoformat()
        trigger_sha = built_commits[0] if built_commits else head_sha

        try:
            for i in range(0, len(paths), self.CHUNK_SIZE):
                chunk = paths[i : i + self.CHUNK_SIZE]
                commits_on_files = repo.git.log(
                    trigger_sha,
                    "--since",
                    start_iso,
                    "--format=%H",
                    "--",
                    *chunk,
                ).splitlines()
                all_shas.update(set(commits_on_files))

            # Exclude commits that are part of this build
            for sha in built_commits:
                all_shas.discard(sha)

        except Exception as e:
            logger.warning(f"Failed to count commits on files: {e}")
            return 0

        return len(all_shas)
