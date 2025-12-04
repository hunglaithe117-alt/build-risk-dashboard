"""
Example: How to add a new feature node to the pipeline.

This file demonstrates the process of adding new features.
"""

# =============================================================================
# STEP 1: Create your feature node file
# =============================================================================
# 
# Create a new file in the appropriate features/ subdirectory:
# - features/git/ for git-related features
# - features/github/ for GitHub API features  
# - features/build_log/ for log parsing features
# - features/repo/ for repository-level features
# - Or create a new subdirectory for a new category

# =============================================================================
# STEP 2: Implement the feature node
# =============================================================================

from typing import Any, Dict

from app.pipeline.features import FeatureNode
from app.pipeline.core.registry import register_feature
from app.pipeline.core.context import ExecutionContext
from app.pipeline.resources import ResourceNames


@register_feature(
    # Unique name for this node
    name="my_new_features",
    
    # Resources this node needs (initialized by ResourceProviders)
    requires_resources={ResourceNames.GIT_REPO},
    
    # Features from OTHER nodes that this node needs
    # The DAG will ensure those nodes run before this one
    requires_features={"git_all_built_commits"},  # From git_commit_info node
    
    # Features this node will produce
    # These become available for downstream nodes
    provides={
        "my_feature_1",
        "my_feature_2",
        "my_derived_feature",
    },
    
    # Logical grouping (for organization)
    group="git",
    
    # Higher priority = runs earlier when possible
    priority=0,
)
class MyNewFeaturesNode(FeatureNode):
    """
    Docstring explaining what this node extracts.
    """
    
    def extract(self, context: ExecutionContext) -> Dict[str, Any]:
        # Access resources
        git_handle = context.get_resource(ResourceNames.GIT_REPO)
        
        # Access features from upstream nodes
        built_commits = context.get_feature("git_all_built_commits", [])
        
        # Access entity data
        build_sample = context.build_sample
        repo = context.repo
        
        # Your extraction logic here
        feature_1 = self._calculate_feature_1(git_handle, built_commits)
        feature_2 = self._calculate_feature_2(repo)
        
        # Derived features
        derived = feature_1 * feature_2 if feature_1 and feature_2 else None
        
        # Return dict with EXACTLY the features declared in 'provides'
        return {
            "my_feature_1": feature_1,
            "my_feature_2": feature_2,
            "my_derived_feature": derived,
        }
    
    def _calculate_feature_1(self, git_handle, commits):
        # Implementation
        return len(commits)
    
    def _calculate_feature_2(self, repo):
        # Implementation
        return 42


# =============================================================================
# STEP 3: Register the node by importing it
# =============================================================================
#
# Add an import in the package __init__.py:
#
# In features/git/__init__.py:
#   from app.pipeline.features.git.my_new_features import MyNewFeaturesNode
#
# In pipeline/runner.py (or wherever pipeline is initialized):
#   from app.pipeline.features.git import MyNewFeaturesNode


# =============================================================================
# STEP 4: Update BuildSample model (if needed)
# =============================================================================
#
# Add the new fields to app/models/entities/build_sample.py:
#
#   class BuildSample(BaseEntity):
#       ...
#       # My new features
#       my_feature_1: int | None = None
#       my_feature_2: int | None = None
#       my_derived_feature: int | None = None


# =============================================================================
# STEP 5: Test your feature node
# =============================================================================
#
# Create a test file in tests/:
#
#   def test_my_new_features_node():
#       # Create mock context
#       context = ExecutionContext(
#           build_sample=mock_build_sample,
#           repo=mock_repo,
#           db=mock_db,
#       )
#       context.set_resource(ResourceNames.GIT_REPO, mock_git_handle)
#       context.merge_features({"git_all_built_commits": ["abc123"]})
#       
#       # Execute node
#       node = MyNewFeaturesNode()
#       features = node.extract(context)
#       
#       # Assert
#       assert "my_feature_1" in features
#       assert features["my_feature_1"] == 1


# =============================================================================
# DEPENDENCY GRAPH VISUALIZATION
# =============================================================================
#
# After adding your node, you can visualize the DAG:
#
#   from app.pipeline.runner import FeaturePipeline
#   pipeline = FeaturePipeline(db)
#   print(pipeline.visualize_dag())
#
# Output will show your node in the correct execution level based on dependencies.
