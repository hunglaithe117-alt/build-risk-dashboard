# Pipeline Core - Simplified for Hamilton
from app.pipeline.core.context import ExecutionContext, FeatureResult
from app.pipeline.core.registry import feature_registry, OutputFormat

__all__ = [
    # Context (backward compatibility)
    "ExecutionContext",
    "FeatureResult",
    # Registry (formatting utility)
    "feature_registry",
    "OutputFormat",
]
