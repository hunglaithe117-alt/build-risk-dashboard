from app.pipeline.resource_dag.dag import (
    get_ingestion_tasks,
    get_resource_dag_runner,
    ResourceDAGRunner,
)

INGESTION_TASK_TO_CELERY = {
    "clone_repo": "app.tasks.model_ingestion.clone_repo",
    "fetch_and_save_builds": "app.tasks.model_ingestion.fetch_and_save_builds",
    "download_build_logs": "app.tasks.model_ingestion.download_build_logs",
    "create_worktrees_batch": "app.tasks.model_ingestion.create_worktrees_batch",
}

__all__ = [
    "get_ingestion_tasks",
    "get_resource_dag_runner",
    "ResourceDAGRunner",
    "INGESTION_TASK_TO_CELERY",
]
