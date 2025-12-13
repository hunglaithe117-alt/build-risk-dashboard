# Feature DAG Pipeline
# A declarative, dependency-aware feature extraction system

from app.pipeline.core.context import ExecutionContext, FeatureResult
from app.pipeline.core.dag import FeatureDAG
from app.pipeline.core.executor import PipelineExecutor
from app.pipeline.core.registry import feature_registry, register_feature

# Import all feature nodes to trigger @register_feature decorator execution
# Without these imports, the decorators never run and providers aren't registered
from app.pipeline.extract_nodes.build_log import workflow_metadata  # noqa: F401
from app.pipeline.extract_nodes.build_log import job_metadata  # noqa: F401
from app.pipeline.extract_nodes.build_log import test_log_parser  # noqa: F401
from app.pipeline.extract_nodes.git import commit_info  # noqa: F401
from app.pipeline.extract_nodes.git import diff_features  # noqa: F401
from app.pipeline.extract_nodes.git import team_membership  # noqa: F401
from app.pipeline.extract_nodes.git import file_touch_history  # noqa: F401
from app.pipeline.extract_nodes.repo import snapshot  # noqa: F401
from app.pipeline.extract_nodes.github import discussion  # noqa: F401

# NOTE: SonarQube and Trivy tools moved to app.integrations module

__all__ = [
    "ExecutionContext",
    "FeatureResult",
    "FeatureDAG",
    "PipelineExecutor",
    "feature_registry",
    "register_feature",
]
