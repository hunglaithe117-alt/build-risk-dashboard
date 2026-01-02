from app.tasks.pipeline.feature_dag.extractors import (
    build,
    ci,
    code,
    collaboration,
    repository,
    temporal,
)

DEFAULT_FEATURES = {"tr_build_id", "gh_project_name", "ci_provider"}

HAMILTON_MODULES = [
    build,
    ci,
    code,
    collaboration,
    repository,
    temporal,
]


def get_input_resource_names() -> frozenset:
    """
    Get all input resource names that should NOT be stored as features.

    These are Hamilton DAG inputs, not actual feature values.
    Derived from INPUT_REGISTRY for single source of truth.
    """
    from app.tasks.pipeline.shared.resources import get_input_resource_names as _get_names

    return _get_names()
