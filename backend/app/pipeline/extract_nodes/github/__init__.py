"""
GitHub Feature Nodes.

Extracts features from GitHub API:
- Discussion/comment metrics
- PR information
"""

from app.pipeline.extract_nodes.github.discussion import GitHubDiscussionNode

__all__ = ["GitHubDiscussionNode"]
