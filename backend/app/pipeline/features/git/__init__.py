"""
Git Feature Nodes.

Extracts features from git repository:
- Commit history and build mapping
- Diff statistics
- Team membership and file history
"""

from app.pipeline.features.git.commit_info import GitCommitInfoNode
from app.pipeline.features.git.diff_features import GitDiffFeaturesNode
from app.pipeline.features.git.team_membership import TeamMembershipNode
from app.pipeline.features.git.file_touch_history import FileTouchHistoryNode

__all__ = [
    "GitCommitInfoNode",
    "GitDiffFeaturesNode",
    "TeamMembershipNode",
    "FileTouchHistoryNode",
]
