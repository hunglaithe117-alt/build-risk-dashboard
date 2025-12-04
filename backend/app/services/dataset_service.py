"""
Dataset Service.

Business logic for Custom Dataset Builder.
Handles feature resolution, dependency calculation, and job management.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from bson import ObjectId
from pymongo.database import Database

from app.models.entities.dataset_job import DatasetJob, DatasetJobStatus
from app.repositories.dataset_job import DatasetJobRepository
from app.repositories.feature_definition import FeatureDefinitionRepository
from app.dtos.dataset import (
    AvailableFeaturesResponse,
    DatasetJobCreateRequest,
    DatasetJobCreatedResponse,
    DatasetJobListResponse,
    DatasetJobResponse,
    FeatureCategoryResponse,
    FeatureDefinitionResponse,
    ResolvedDependenciesResponse,
)

logger = logging.getLogger(__name__)


# Category display names
CATEGORY_DISPLAY_NAMES = {
    "build_log": "Build Log Analysis",
    "git_diff": "Git Diff Metrics",
    "git_history": "Git History",
    "team": "Team Statistics",
    "discussion": "GitHub Discussions",
    "repo_snapshot": "Repository Snapshot",
    "metadata": "Build Metadata",
    "pr_info": "Pull Request Info",
}

# Features that are always included in every dataset (not shown in UI selection)
DEFAULT_FEATURES = [
    "tr_build_id",
    "gh_project_name", 
    "git_trigger_commit",
]

# Features that require source_languages to be set on the repository
FEATURES_REQUIRING_SOURCE_LANGUAGES = [
    # From build_log_extractor
    "tr_log_lan_all",
    # From git_feature_extractor (diff features)
    "git_diff_src_churn",
    "git_diff_test_churn", 
    "gh_diff_files_added",
    "gh_diff_files_deleted",
    "gh_diff_files_modified",
    "gh_diff_src_files",
    "gh_diff_tests_added",
    "gh_diff_tests_deleted",
    # From repo_snapshot_extractor
    "gh_sloc",
    "gh_test_lines_per_kloc",
    "gh_test_cases_per_kloc",
]


class DatasetService:
    """Service for managing custom dataset jobs."""
    
    def __init__(self, db: Database):
        self.db = db
        self.job_repo = DatasetJobRepository(db)
        self.feature_repo = FeatureDefinitionRepository(db)
    
    # ====================
    # Feature Discovery
    # ====================
    
    def get_available_features(self, ml_only: bool = False) -> AvailableFeaturesResponse:
        """
        Get all available features grouped by category.
        
        Args:
            ml_only: If True, only return ML features
        """
        features = self.feature_repo.find_active()
        if ml_only:
            features = [f for f in features if f.is_ml_feature]
        
        # Filter out default features (they are always included, no need to select)
        features = [f for f in features if f.name not in DEFAULT_FEATURES]
        
        # Build name-to-id map for dependencies
        name_to_id = {f.name: str(f.id) for f in features}
        
        # Group by category
        categories_map: Dict[str, List[FeatureDefinitionResponse]] = {}
        for f in features:
            cat = f.category
            if cat not in categories_map:
                categories_map[cat] = []
            
            # Determine requires_clone and requires_log from depends_on_resources
            requires_clone = "git_repo" in (f.depends_on_resources or [])
            requires_log = "log_storage" in (f.depends_on_resources or [])
            
            # Convert dependency names to IDs
            dep_ids = [name_to_id.get(dep, dep) for dep in (f.depends_on_features or [])]
            
            categories_map[cat].append(FeatureDefinitionResponse(
                id=str(f.id),
                slug=f.name,  # Use 'name' field as slug
                name=f.display_name,
                description=f.description or "",
                category=f.category,
                data_type=f.data_type,
                is_ml_feature=f.is_ml_feature,
                dependencies=dep_ids,
                extractor_node=f.extractor_node,
                requires_clone=requires_clone,
                requires_log=requires_log,
            ))
        
        # Build response
        categories = []
        for cat, cat_features in sorted(categories_map.items()):
            categories.append(FeatureCategoryResponse(
                category=cat,
                display_name=CATEGORY_DISPLAY_NAMES.get(cat, cat.replace("_", " ").title()),
                features=sorted(cat_features, key=lambda x: x.name),
            ))
        
        ml_count = sum(1 for f in features if f.is_ml_feature)
        
        return AvailableFeaturesResponse(
            categories=categories,
            total_features=len(features),
            ml_features_count=ml_count,
            default_features=DEFAULT_FEATURES,
            features_requiring_source_languages=FEATURES_REQUIRING_SOURCE_LANGUAGES,
        )
    
    # ====================
    # Dependency Resolution
    # ====================
    
    def resolve_dependencies(
        self, 
        feature_ids: List[str]
    ) -> ResolvedDependenciesResponse:
        """
        Resolve feature dependencies and calculate required resources.
        
        This is the core optimization logic:
        1. Expand selected features to include all dependencies
        2. Determine minimal set of extractor nodes needed
        3. Calculate resource requirements
        """
        # Build feature maps (by ID and by name)
        all_features = self.feature_repo.find_active()
        id_to_feature = {str(f.id): f for f in all_features}
        name_to_feature = {f.name: f for f in all_features}
        name_to_id = {f.name: str(f.id) for f in all_features}
        
        # Validate selected feature IDs
        invalid = [fid for fid in feature_ids if fid not in id_to_feature]
        if invalid:
            raise ValueError(f"Invalid feature IDs: {invalid}")
        
        # Resolve dependencies using BFS (working with feature names internally)
        resolved_names: Set[str] = set()
        
        # Start with selected features
        queue = [id_to_feature[fid].name for fid in feature_ids]
        
        # Always include default features
        for default_feature in DEFAULT_FEATURES:
            if default_feature in name_to_feature:
                queue.append(default_feature)
        
        while queue:
            feature_name = queue.pop(0)
            if feature_name in resolved_names:
                continue
            resolved_names.add(feature_name)
            
            feature = name_to_feature.get(feature_name)
            if feature and feature.depends_on_features:
                for dep in feature.depends_on_features:
                    if dep not in resolved_names:
                        queue.append(dep)
        
        # Determine required nodes and resources
        required_nodes: Set[str] = set()
        requires_clone = False
        requires_log = False
        
        for feature_name in resolved_names:
            feature = name_to_feature[feature_name]
            required_nodes.add(feature.extractor_node)
            
            # Check resource requirements
            resources = feature.depends_on_resources or []
            if "git_repo" in resources:
                requires_clone = True
            if "log_storage" in resources:
                requires_log = True
        
        # Check if any features require source_languages
        features_needing_source_langs = [
            f for f in resolved_names if f in FEATURES_REQUIRING_SOURCE_LANGUAGES
        ]
        requires_source_languages = len(features_needing_source_langs) > 0
        
        # Convert resolved names to IDs
        resolved_ids = [name_to_id[n] for n in resolved_names if n in name_to_id]
        
        return ResolvedDependenciesResponse(
            selected_feature_ids=feature_ids,
            resolved_feature_ids=sorted(resolved_ids),
            resolved_feature_names=sorted(resolved_names),
            required_nodes=sorted(required_nodes),
            requires_clone=requires_clone,
            requires_log_collection=requires_log,
            requires_source_languages=requires_source_languages,
            features_needing_source_languages=sorted(features_needing_source_langs),
        )
    
    # ====================
    # Job Management
    # ====================
    
    def create_job(
        self,
        user_id: str,
        request: DatasetJobCreateRequest,
    ) -> DatasetJobCreatedResponse:
        """
        Create a new dataset extraction job.
        
        1. Validates features exist
        2. Resolves dependencies
        3. Validates source_languages if required
        4. Creates job record
        5. Queues Celery task
        """
        resolved = self.resolve_dependencies(request.feature_ids)
        
        # Validate source_languages if required
        if resolved.requires_source_languages and not request.source_languages:
            raise ValueError(
                f"source_languages is required for the following features: "
                f"{', '.join(resolved.features_needing_source_languages)}"
            )
        
        # Parse repo URL to get full_name
        from app.tasks.dataset import parse_github_url
        repo_info = parse_github_url(request.repo_url)
        repo_full_name = repo_info["full_name"] if repo_info else ""
        
        # Create job entity (exclude _id for new document)
        job_data = {
            "user_id": ObjectId(user_id),
            "repo_full_name": repo_full_name,
            "repo_url": request.repo_url,
            "max_builds": request.max_builds,
            "selected_features": resolved.resolved_feature_names,  # Store names for extraction
            "resolved_features": resolved.resolved_feature_names,
            "required_nodes": resolved.required_nodes,
            "requires_clone": resolved.requires_clone,
            "requires_log": resolved.requires_log_collection,
            "source_languages": request.source_languages,
            "status": DatasetJobStatus.PENDING.value,
            "current_phase": "queued",
            "total_builds": 0,
            "processed_builds": 0,
            "failed_builds": 0,
            "created_at": datetime.now(timezone.utc),
        }
        
        created = self.job_repo.insert_one(job_data)
        job_id = str(created.id)
        
        # Queue Celery task
        from app.tasks.dataset import process_dataset_job
        process_dataset_job.delay(job_id)
        
        # Estimate time
        return DatasetJobCreatedResponse(
            job_id=job_id,
            message="Dataset job created and queued for processing",
            status=DatasetJobStatus.PENDING.value,
            estimated_time_minutes=None,
        )
    
    def get_job(self, job_id: str, user_id: str) -> DatasetJobResponse:
        """Get job details with ownership check."""
        job = self.job_repo.find_by_id(ObjectId(job_id))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if str(job.user_id) != user_id:
            raise PermissionError("You don't have access to this job")
        
        return self._to_response(job)
    
    def list_jobs(
        self,
        user_id: str,
        page: int = 1,
        page_size: int = 20,
        status: Optional[DatasetJobStatus] = None,
    ) -> DatasetJobListResponse:
        """List user's jobs with pagination."""
        skip = (page - 1) * page_size
        jobs, total = self.job_repo.find_by_user(
            user_id, 
            skip=skip, 
            limit=page_size,
            status=status,
        )
        
        total_pages = (total + page_size - 1) // page_size
        
        return DatasetJobListResponse(
            items=[self._to_response(j) for j in jobs],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )
    
    def cancel_job(self, job_id: str, user_id: str) -> DatasetJobResponse:
        """Cancel a pending or processing job."""
        job = self.job_repo.find_by_id(ObjectId(job_id))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if str(job.user_id) != user_id:
            raise PermissionError("You don't have access to this job")
        
        if job.status in [DatasetJobStatus.COMPLETED.value, DatasetJobStatus.FAILED.value]:
            raise ValueError("Cannot cancel completed/failed job")
        
        updated = self.job_repo.update_status(
            job_id,
            DatasetJobStatus.FAILED,
            error_message="Cancelled by user",
        )
        
        if not updated:
            raise ValueError(f"Failed to update job: {job_id}")
        
        return self._to_response(updated)
    
    def delete_job(self, job_id: str, user_id: str) -> bool:
        """Delete a job and its output file."""
        from app.repositories.dataset_sample import DatasetSampleRepository
        
        job = self.job_repo.find_by_id(ObjectId(job_id))
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        if str(job.user_id) != user_id:
            raise PermissionError("You don't have access to this job")
        
        # Delete output file if exists
        if job.output_file_path:
            import os
            try:
                if os.path.exists(job.output_file_path):
                    os.remove(job.output_file_path)
            except Exception as e:
                logger.warning(f"Failed to delete output file: {e}")
        
        # Delete associated dataset samples
        sample_repo = DatasetSampleRepository(self.db)
        deleted_samples = sample_repo.delete_by_job_id(job_id)
        logger.info(f"Deleted {deleted_samples} dataset samples for job {job_id}")
        
        return self.job_repo.delete_one(job_id)
    
    # ====================
    # Helpers
    # ====================
    
    def _to_response(self, job: DatasetJob) -> DatasetJobResponse:
        """Convert entity to response DTO."""
        progress_percent = 0.0
        if job.total_builds > 0:
            progress_percent = round(
                (job.processed_builds / job.total_builds) * 100, 1
            )
        
        return DatasetJobResponse(
            id=str(job.id),
            user_id=str(job.user_id),
            repo_url=job.repo_url,
            max_builds=job.max_builds,
            selected_features=job.selected_features,
            resolved_features=job.resolved_features,
            required_nodes=job.required_nodes,
            status=job.status.value if isinstance(job.status, DatasetJobStatus) else job.status,
            current_phase=job.current_phase or "",
            total_builds=job.total_builds,
            processed_builds=job.processed_builds,
            failed_builds=job.failed_builds,
            progress_percent=progress_percent,
            output_file_path=job.output_file_path,
            output_file_size=job.output_file_size,
            output_row_count=job.output_row_count,
            download_count=job.download_count or 0,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            error_message=job.error_message,
        )
