"""
Git Commit Info Node.

Extracts commit-related features:
- All commits included in this build
- Previous built commit
- Resolution status
"""

import logging
from typing import Any, Dict, List, Optional

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature, OutputFormat
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle
from app.pipeline.utils.git_utils import (
    get_commit_parents,
    iter_commit_history,
)

logger = logging.getLogger(__name__)


@register_feature(
    name="git_commit_info",
    requires_resources={ResourceNames.GIT_REPO},
    provides={
        "git_all_built_commits",
        "git_num_all_built_commits",
        "git_prev_built_commit",
        "git_prev_commit_resolution_status",
        "tr_prev_build",
    },
    group="git",
    priority=10,
    output_formats={
        "git_all_built_commits": OutputFormat.HASH_SEPARATED,
    },
)
class GitCommitInfoNode(FeatureNode):
    """
    Determines which commits are part of this build.
    """

    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        git_handle: GitRepoHandle = context.get_resource(ResourceNames.GIT_REPO)
        build_sample = context.build_sample
        db = context.db

        if not git_handle.is_commit_available:
            return {
                "git_all_built_commits": [],
                "git_num_all_built_commits": 0,
                "git_prev_built_commit": None,
                "git_prev_commit_resolution_status": "commit_not_found",
                "tr_prev_build": None,
            }

        effective_sha = git_handle.effective_sha
        repo = git_handle.repo
        repo_path = git_handle.path

        # We need to find the previous *built* commit in the history of THIS commit
        # This requires walking back from effective_sha until we find a commit that constitutes a completed build

        build_stats = self._calculate_build_stats(
            db, build_sample, repo, repo_path, effective_sha
        )

        return build_stats

    def _calculate_build_stats(
        self, db, build_sample, repo, repo_path, commit_sha: str
    ) -> Dict[str, Any]:
        commits_hex: List[str] = [commit_sha]
        status = "no_previous_build"
        last_commit_sha: Optional[str] = None
        prev_build_id = None

        build_coll = db["build_samples"]

        from bson import ObjectId

        repo_id_query = build_sample.repo_id
        try:
            if isinstance(repo_id_query, str):
                repo_id_query = ObjectId(repo_id_query)
        except Exception:
            pass

        walker = None
        use_subprocess = False

        try:
            walker = repo.iter_commits(commit_sha, max_count=1000)
        except Exception as e:
            logger.info(
                f"GitPython iter_commits failed, using subprocess fallback: {e}"
            )
            use_subprocess = True

        if use_subprocess:
            # Subprocess fallback
            return self._calculate_build_stats_subprocess(
                build_coll, build_sample, repo_path, commit_sha, repo_id_query
            )

        # Use GitPython walker
        first = True
        for commit in walker:
            try:
                hexsha = commit.hexsha

                if first:
                    # Check if merge - try GitPython first, then subprocess
                    try:
                        parents = commit.parents
                        if len(parents) > 1:
                            status = "merge_found"
                            break
                    except Exception:
                        # Fallback to subprocess for parents
                        parents = get_commit_parents(repo_path, hexsha)
                        if len(parents) > 1:
                            status = "merge_found"
                            break
                    first = False
                    continue

                last_commit_sha = hexsha

                # Check if this commit triggered a build
                existing_build = build_coll.find_one(
                    {
                        "repo_id": repo_id_query,
                        "tr_original_commit": hexsha,
                        "status": "completed",
                        "workflow_run_id": {"$ne": build_sample.workflow_run_id},
                    }
                )

                if existing_build:
                    status = "build_found"
                    prev_build_id = existing_build.get("workflow_run_id")
                    break

                commits_hex.append(hexsha)

                # Check merge - try GitPython first, then subprocess
                try:
                    if len(commit.parents) > 1:
                        status = "merge_found"
                        break
                except Exception:
                    parents = get_commit_parents(repo_path, hexsha)
                    if len(parents) > 1:
                        status = "merge_found"
                        break
            except Exception as e:
                logger.warning(f"Error processing commit in history: {e}")
                break  # Stop iteration on error

        return {
            "git_prev_commit_resolution_status": status,
            "git_prev_built_commit": last_commit_sha,
            "tr_prev_build": prev_build_id,
            "git_all_built_commits": commits_hex,
            "git_num_all_built_commits": len(commits_hex),
        }

    def _calculate_build_stats_subprocess(
        self, build_coll, build_sample, repo_path, commit_sha: str, repo_id_query
    ) -> Dict[str, Any]:
        """Calculate build stats using subprocess when GitPython fails."""
        commits_hex: List[str] = [commit_sha]
        status = "no_previous_build"
        last_commit_sha: Optional[str] = None
        prev_build_id = None

        first = True
        for commit_info in iter_commit_history(repo_path, commit_sha, max_count=1000):
            hexsha = commit_info["hexsha"]
            parents = commit_info["parents"]

            if first:
                if len(parents) > 1:
                    status = "merge_found"
                    break
                first = False
                continue

            last_commit_sha = hexsha

            # Check if this commit triggered a build
            existing_build = build_coll.find_one(
                {
                    "repo_id": repo_id_query,
                    "tr_original_commit": hexsha,
                    "status": "completed",
                    "workflow_run_id": {"$ne": build_sample.workflow_run_id},
                }
            )

            if existing_build:
                status = "build_found"
                prev_build_id = existing_build.get("workflow_run_id")
                break

            commits_hex.append(hexsha)

            if len(parents) > 1:
                status = "merge_found"
                break

        return {
            "git_prev_commit_resolution_status": status,
            "git_prev_built_commit": last_commit_sha,
            "tr_prev_build": prev_build_id,
            "git_all_built_commits": commits_hex,
            "git_num_all_built_commits": len(commits_hex),
        }
