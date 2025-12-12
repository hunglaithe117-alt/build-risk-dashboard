from enum import Enum

from .base_build import BaseBuildSample


class ModelBuildConclusion(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"
    TIMED_OUT = "timed_out"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class ModelBuild(BaseBuildSample):
    build_conclusion: ModelBuildConclusion = ModelBuildConclusion.SUCCESS

    class Config:
        collection = "model_builds"
        use_enum_values = True
