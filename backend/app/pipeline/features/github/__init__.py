"""
GitHub Feature Nodes.

Extracts features from GitHub API:
- Discussion/comment metrics
- PR information
"""

from app.pipeline.features.github.discussion import GitHubDiscussionNode

__all__ = ["GitHubDiscussionNode"]
