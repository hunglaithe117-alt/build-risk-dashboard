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
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames
from app.pipeline.resources.git_repo import GitRepoHandle
from app.repositories.build_sample import BuildSampleRepository

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
    priority=10,  # Run early as other git features depend on this
)
class GitCommitInfoNode(FeatureNode):
    """
    Determines which commits are part of this build.
    
    A build may include multiple commits if:
    - Multiple commits pushed before CI triggered
    - Force push with new commits
    - Merge commits
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
        repo_id = str(build_sample.repo_id)
        
        # Find previous built commit
        build_sample_repo = BuildSampleRepository(db)
        prev_build = self._find_previous_build(build_sample_repo, build_sample)
        
        prev_built_commit = None
        tr_prev_build = None
        resolution_status = "first_build"
        
        if prev_build:
            prev_built_commit = prev_build.tr_original_commit
            tr_prev_build = prev_build.workflow_run_id
            resolution_status = "found"
        
        # Calculate commits between prev and current
        built_commits = []
        if prev_built_commit:
            built_commits = self._get_commits_between(
                git_handle, prev_built_commit, effective_sha
            )
            if not built_commits:
                # Commits not in same lineage - could be branch switch
                resolution_status = "not_in_lineage"
                built_commits = [effective_sha]
        else:
            built_commits = [effective_sha]
        
        return {
            "git_all_built_commits": built_commits,
            "git_num_all_built_commits": len(built_commits),
            "git_prev_built_commit": prev_built_commit,
            "git_prev_commit_resolution_status": resolution_status,
            "tr_prev_build": tr_prev_build,
        }
    
    def _find_previous_build(self, repo, build_sample) -> Optional[Any]:
        """Find the most recent completed build before this one."""
        # Query for builds before this one
        query = {
            "repo_id": build_sample.repo_id,
            "workflow_run_id": {"$lt": build_sample.workflow_run_id},
            "status": "completed",
        }
        
        prev_builds = list(
            repo.collection.find(query)
            .sort("workflow_run_id", -1)
            .limit(1)
        )
        
        if prev_builds:
            from app.models.entities.build_sample import BuildSample
            return BuildSample(**prev_builds[0])
        return None
    
    def _get_commits_between(
        self, 
        git_handle: GitRepoHandle, 
        from_sha: str, 
        to_sha: str
    ) -> List[str]:
        """Get all commits between two SHAs (exclusive from, inclusive to)."""
        try:
            repo = git_handle.repo
            
            # Check if both commits exist
            try:
                from_commit = repo.commit(from_sha)
                to_commit = repo.commit(to_sha)
            except Exception:
                return []
            
            # Get commits in range
            commits = list(repo.iter_commits(f"{from_sha}..{to_sha}"))
            return [c.hexsha for c in commits]
            
        except Exception as e:
            logger.warning(f"Failed to get commits between {from_sha} and {to_sha}: {e}")
            return []
