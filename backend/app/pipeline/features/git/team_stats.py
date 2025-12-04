"""
Team Stats Feature Node.

Extracts team-related metrics:
- Team size
- Core team membership
- File touch history
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
    name="team_stats_features",
    requires_resources={ResourceNames.GIT_REPO},
    requires_features={"git_all_built_commits"},
    provides={
        "gh_team_size",
        "gh_by_core_team_member",
        "gh_num_commits_on_files_touched",
    },
    group="git",
)
class TeamStatsNode(FeatureNode):
    """
    Calculates team-related metrics.
    
    - Team size: unique contributors in last 3 months
    - Core team: author contributed ≥5% of commits in last 3 months
    - File history: total commits on files touched by this build
    """
    
    LOOKBACK_DAYS = 90
    CORE_TEAM_THRESHOLD = 0.05  # 5% of commits
    
    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        git_handle: GitRepoHandle = context.get_resource(ResourceNames.GIT_REPO)
        
        if not git_handle.is_commit_available:
            return self._empty_result()
        
        repo = git_handle.repo
        effective_sha = git_handle.effective_sha
        built_commits = context.get_feature("git_all_built_commits", [])
        
        # Get current commit for author info
        try:
            current_commit = repo.commit(effective_sha)
        except Exception:
            return self._empty_result()
        
        author_email = current_commit.author.email
        
        # Calculate team stats
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.LOOKBACK_DAYS)
        
        contributor_commits: Dict[str, int] = {}
        total_commits = 0
        
        try:
            for commit in repo.iter_commits(effective_sha, since=cutoff):
                email = commit.author.email
                contributor_commits[email] = contributor_commits.get(email, 0) + 1
                total_commits += 1
        except Exception as e:
            logger.warning(f"Failed to iterate commits for team stats: {e}")
            return self._empty_result()
        
        team_size = len(contributor_commits)
        
        # Core team membership
        is_core_team = False
        if total_commits > 0 and author_email in contributor_commits:
            contribution_rate = contributor_commits[author_email] / total_commits
            is_core_team = contribution_rate >= self.CORE_TEAM_THRESHOLD
        
        # File touch history
        num_commits_on_files = self._calculate_file_history(
            repo, built_commits, effective_sha
        )
        
        return {
            "gh_team_size": team_size,
            "gh_by_core_team_member": is_core_team,
            "gh_num_commits_on_files_touched": num_commits_on_files,
        }
    
    def _calculate_file_history(
        self, 
        repo, 
        built_commits: List[str],
        head_sha: str,
    ) -> int:
        """Calculate total commits on files touched by this build."""
        # Get files changed in this build
        touched_files: Set[str] = set()
        
        for sha in built_commits:
            try:
                commit = repo.commit(sha)
                if commit.parents:
                    diff = commit.diff(commit.parents[0])
                    for d in diff:
                        if d.a_path:
                            touched_files.add(d.a_path)
                        if d.b_path:
                            touched_files.add(d.b_path)
            except Exception:
                continue
        
        if not touched_files:
            return 0
        
        # Count commits touching these files
        total_touches = 0
        try:
            for commit in repo.iter_commits(head_sha, max_count=1000):
                if commit.parents:
                    try:
                        diff = commit.diff(commit.parents[0])
                        files_in_commit = {d.a_path for d in diff if d.a_path}
                        files_in_commit.update({d.b_path for d in diff if d.b_path})
                        
                        if files_in_commit & touched_files:
                            total_touches += 1
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"Failed to calculate file history: {e}")
        
        return total_touches
    
    def _empty_result(self) -> Dict[str, Any]:
        return {
            "gh_team_size": None,
            "gh_by_core_team_member": None,
            "gh_num_commits_on_files_touched": None,
        }
