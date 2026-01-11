"""
Training Scenario Service - Business logic for Training Pipeline.

Handles:
- YAML config parsing and validation
- Scenario CRUD operations
- Pipeline orchestration (Ingestion → Processing → Generation)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import yaml
from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.database import Database

from app import paths
from app.dtos.training_scenario import (
    DataSourceConfigDTO,
    FeatureConfigDTO,
    OutputConfigDTO,
    PreprocessingConfigDTO,
    SplittingConfigDTO,
    TrainingScenarioCreate,
    TrainingScenarioResponse,
    TrainingScenarioUpdate,
)
from app.entities.training_dataset_split import TrainingDatasetSplit
from app.entities.training_scenario import (
    DataSourceConfig,
    FeatureConfig,
    OutputConfig,
    PreprocessingConfig,
    ScenarioStatus,
    SplittingConfig,
    TrainingScenario,
)
from app.repositories.raw_build_run import RawBuildRunRepository
from app.repositories.raw_repository import RawRepositoryRepository
from app.repositories.training_dataset_split import TrainingDatasetSplitRepository
from app.repositories.training_enrichment_build import TrainingEnrichmentBuildRepository
from app.repositories.training_ingestion_build import TrainingIngestionBuildRepository
from app.repositories.training_scenario import TrainingScenarioRepository

logger = logging.getLogger(__name__)


class TrainingScenarioService:
    """Service for Training Scenario operations."""

    def __init__(self, db: Database):
        self.db = db
        self.scenario_repo = TrainingScenarioRepository(db)
        self.ingestion_build_repo = TrainingIngestionBuildRepository(db)
        self.enrichment_build_repo = TrainingEnrichmentBuildRepository(db)
        self.split_repo = TrainingDatasetSplitRepository(db)

        # Legacy/Raw repos
        self.raw_repo_repo = RawRepositoryRepository(db)
        self.raw_build_run_repo = RawBuildRunRepository(db)

    # =========================================================================
    # CRUD Operations
    # =========================================================================

    def list_scenarios(
        self,
        skip: int = 0,
        limit: int = 20,
        status_filter: Optional[ScenarioStatus] = None,
        q: Optional[str] = None,
    ) -> Tuple[List[TrainingScenarioResponse], int]:
        """List all scenarios (shared among all admins)."""
        scenarios, total = self.scenario_repo.list_all(
            skip=skip,
            limit=limit,
            status_filter=status_filter,
            q=q,
        )
        return [self._to_response(s) for s in scenarios], total

    def get_scenario(
        self,
        scenario_id: str,
        user_id: str,
    ) -> TrainingScenarioResponse:
        """Get scenario details."""
        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )

        # Optional: Permission check if ownership enforced
        # if scenario.created_by and str(scenario.created_by) != user_id: ...

        return self._to_response(scenario)

    def create_scenario(
        self,
        user_id: str,
        data: TrainingScenarioCreate,
    ) -> TrainingScenarioResponse:
        """Create a new scenario from YAML config."""
        # Check for duplicate name
        existing = self.scenario_repo.find_by_name(data.name, user_id)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Scenario with name '{data.name}' already exists",
            )

        # Parse and validate YAML
        parsed_config = self._parse_yaml_config(data.yaml_config)

        # Create scenario entity
        scenario = TrainingScenario(
            name=data.name,
            description=data.description,
            version=parsed_config.get("version", data.version),
            yaml_config=data.yaml_config,
            data_source_config=self._parse_data_source_config(
                parsed_config.get("data_source", {})
            ),
            feature_config=self._parse_feature_config(
                parsed_config.get("features", {})
            ),
            splitting_config=self._parse_splitting_config(
                parsed_config.get("splitting", {})
            ),
            preprocessing_config=self._parse_preprocessing_config(
                parsed_config.get("preprocessing", {})
            ),
            output_config=self._parse_output_config(parsed_config.get("output", {})),
            status=ScenarioStatus.QUEUED,
            created_by=ObjectId(user_id),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        created = self.scenario_repo.insert_one(scenario)

        # Create scenario directory
        scenario_dir = paths.get_training_scenario_dir(str(created.id))
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Save YAML config file
        config_path = paths.get_training_scenario_config_path(str(created.id))
        config_path.write_text(data.yaml_config)

        logger.info(f"Created TrainingScenario: {created.id} - {data.name}")
        return self._to_response(created)

    def update_scenario(
        self,
        scenario_id: str,
        user_id: str,
        data: TrainingScenarioUpdate,
    ) -> TrainingScenarioResponse:
        """Update scenario fields."""
        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )

        # Cannot update if processing rules apply (e.g. actively running)
        if scenario.status in (
            ScenarioStatus.FILTERING,
            ScenarioStatus.INGESTING,
            ScenarioStatus.PROCESSING,
            ScenarioStatus.SPLITTING,
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot update scenario while pipeline is running",
            )

        updates: Dict[str, Any] = {"updated_at": datetime.utcnow()}

        if data.name is not None:
            existing = self.scenario_repo.find_by_name(data.name, user_id)
            if existing and str(existing.id) != scenario_id:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Scenario with name '{data.name}' already exists",
                )
            updates["name"] = data.name

        if data.description is not None:
            updates["description"] = data.description

        if data.yaml_config is not None:
            parsed_config = self._parse_yaml_config(data.yaml_config)
            updates["yaml_config"] = data.yaml_config
            updates["data_source_config"] = self._parse_data_source_config(
                parsed_config.get("data_source", {})
            ).model_dump()
            updates["feature_config"] = self._parse_feature_config(
                parsed_config.get("features", {})
            ).model_dump()
            updates["splitting_config"] = self._parse_splitting_config(
                parsed_config.get("splitting", {})
            ).model_dump()
            updates["preprocessing_config"] = self._parse_preprocessing_config(
                parsed_config.get("preprocessing", {})
            ).model_dump()
            updates["output_config"] = self._parse_output_config(
                parsed_config.get("output", {})
            ).model_dump()

            # Update saved config file
            config_path = paths.get_training_scenario_config_path(scenario_id)
            config_path.write_text(data.yaml_config)

            # Reset status to QUEUED if config changed
            updates["status"] = ScenarioStatus.QUEUED.value

            # Reset completion flags
            updates["feature_extraction_completed"] = False
            updates["scan_extraction_completed"] = False

        updated = self.scenario_repo.update_one(scenario_id, updates)
        return self._to_response(updated)

    def delete_scenario(
        self,
        scenario_id: str,
        user_id: str,
    ) -> bool:
        """Delete a scenario and all associated data."""
        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Scenario {scenario_id} not found",
            )

        # Delete associated data
        self.ingestion_build_repo.delete_by_scenario(scenario_id)
        self.enrichment_build_repo.delete_by_scenario(scenario_id)
        self.split_repo.delete_by_scenario(scenario_id)

        # Delete Scans
        from app.repositories.sonar_commit_scan import SonarCommitScanRepository
        from app.repositories.trivy_commit_scan import TrivyCommitScanRepository

        trivy_repo = TrivyCommitScanRepository(self.db)
        sonar_repo = SonarCommitScanRepository(self.db)

        trivy_repo.delete_by_scenario(scenario_id)
        sonar_repo.delete_by_scenario(scenario_id)

        # Delete Audit Logs
        from app.repositories.feature_audit_log import FeatureAuditLogRepository

        audit_repo = FeatureAuditLogRepository(self.db)
        audit_repo.delete_by_scenario(scenario_id)

        # Delete Feature Vectors
        from app.repositories.feature_vector import FeatureVectorRepository

        fv_repo = FeatureVectorRepository(self.db)
        fv_repo.delete_by_scenario(scenario_id)

        # Delete files
        paths.cleanup_training_scenario_files(scenario_id)

        # Delete scenario
        self.scenario_repo.delete_one(scenario_id)

        logger.info(f"Deleted TrainingScenario: {scenario_id} and all related entities")
        return True

    # =========================================================================
    # Pipeline Orchestration
    # =========================================================================

    def start_ingestion(self, scenario_id: str, user_id: str) -> Dict[str, Any]:
        """Phase 1: Start ingestion."""
        from app.tasks.training_ingestion import start_scenario_ingestion

        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Allow retry if Failed or Queued
        if scenario.status not in [
            ScenarioStatus.QUEUED.value,
            ScenarioStatus.FAILED.value,
            ScenarioStatus.INGESTED.value,
        ]:
            # If already ingested, user might want to re-ingest?
            # Currently we enforce strict flow or re-ingest if FAILED.
            # If COMPLETED, user should probably create new scenario or we allow re-run.
            # Assuming linear flow for now: QUEUED/FAILED -> INGESTING
            pass

        res = start_scenario_ingestion.delay(scenario_id)
        return {"status": "queued", "task_id": res.id}

    def start_processing(self, scenario_id: str, user_id: str) -> Dict[str, Any]:
        """Phase 2: Start processing."""
        from app.tasks.training_processing import start_scenario_processing

        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Must be INGESTED (or PROCESSED/FAILED to retry)
        if scenario.status not in [
            ScenarioStatus.INGESTED.value,
            ScenarioStatus.PROCESSED.value,
            ScenarioStatus.FAILED.value,
        ]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Scenario must be INGESTED to start processing (current: {scenario.status})"
                ),
            )

        res = start_scenario_processing.delay(scenario_id)
        return {"status": "queued", "task_id": res.id}

    def generate_dataset(self, scenario_id: str, user_id: str) -> Dict[str, Any]:
        """Phase 3: Generate Dataset (Split + Download)."""
        from app.tasks.training_processing import generate_scenario_dataset

        scenario = self.scenario_repo.find_by_id(scenario_id)
        if not scenario:
            raise HTTPException(status_code=404, detail="Scenario not found")

        # Must be PROCESSED (or COMPLETED to re-gen)
        if scenario.status not in [
            ScenarioStatus.PROCESSED.value,
            ScenarioStatus.COMPLETED.value,
        ]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Scenario must be PROCESSED to generate dataset (current: {scenario.status})"
                ),
            )

        res = generate_scenario_dataset.delay(scenario_id)
        return {"status": "queued", "task_id": res.id}

    # =========================================================================
    # Helpers
    # =========================================================================

    def _to_response(self, scenario: TrainingScenario) -> TrainingScenarioResponse:
        """Convert entity to DTO response."""
        return TrainingScenarioResponse(
            id=str(scenario.id),
            name=scenario.name,
            description=scenario.description,
            version=scenario.version,
            status=scenario.status,
            error_message=scenario.error_message,
            # Configs
            data_source_config=DataSourceConfigDTO(
                **scenario.data_source_config.model_dump()
            ),
            feature_config=FeatureConfigDTO(**scenario.feature_config.model_dump()),
            splitting_config=SplittingConfigDTO(
                **scenario.splitting_config.model_dump()
            ),
            preprocessing_config=PreprocessingConfigDTO(
                **scenario.preprocessing_config.model_dump()
            ),
            output_config=OutputConfigDTO(**scenario.output_config.model_dump()),
            yaml_config=scenario.yaml_config,
            # Stats
            builds_total=scenario.builds_total,
            builds_ingested=scenario.builds_ingested,
            builds_features_extracted=scenario.builds_features_extracted,
            builds_missing_resource=scenario.builds_missing_resource,
            builds_failed=scenario.builds_failed,
            scans_total=scenario.scans_total,
            scans_completed=scenario.scans_completed,
            scans_failed=scenario.scans_failed,
            train_count=scenario.train_count,
            val_count=scenario.val_count,
            test_count=scenario.test_count,
            created_by=str(scenario.created_by) if scenario.created_by else None,
            created_at=scenario.created_at,
            updated_at=scenario.updated_at,
            filtering_completed_at=scenario.filtering_completed_at,
            ingestion_completed_at=scenario.ingestion_completed_at,
            processing_completed_at=scenario.processing_completed_at,
            splitting_completed_at=scenario.splitting_completed_at,
            feature_extraction_completed=scenario.feature_extraction_completed,
            scan_extraction_completed=scenario.scan_extraction_completed,
        )

    def _parse_yaml_config(self, yaml_string: str) -> Dict[str, Any]:
        """Parse and validate YAML configuration."""
        try:
            config = yaml.safe_load(yaml_string)
            if not isinstance(config, dict):
                raise HTTPException(
                    status_code=400, detail="YAML config must be a dictionary"
                )
            return config
        except yaml.YAMLError as e:
            raise HTTPException(
                status_code=400, detail=f"Invalid YAML syntax: {str(e)}"
            ) from e

    def _parse_data_source_config(self, config: Dict[str, Any]) -> DataSourceConfig:
        """Parse data_source section."""
        # Mapping logic matching MLScenarioService but for new entities
        try:
            repo_cfg = config.get("repositories", {})
            builds_cfg = config.get("builds", {})
            date_range = builds_cfg.get("date_range", {})

            return DataSourceConfig(
                filter_by=repo_cfg.get("filter_by", "all"),
                languages=repo_cfg.get("languages", []),
                repo_names=repo_cfg.get("names", []),
                owners=repo_cfg.get("owners", []),
                date_start=self._parse_date(date_range.get("start")),
                date_end=self._parse_date(date_range.get("end")),
                conclusions=builds_cfg.get("conclusions", ["success", "failure"]),
                exclude_bots=builds_cfg.get("exclude_bots", True),
                ci_provider=config.get("ci_provider", "all"),
            )
        except Exception:
            # Fallback or re-raise
            return DataSourceConfig()

    def _parse_feature_config(self, config: Dict[str, Any]) -> FeatureConfig:
        return FeatureConfig(**config)

    def _parse_splitting_config(self, config: Dict[str, Any]) -> SplittingConfig:
        # Flatten structure if nested under 'config' key in YAML
        if "config" in config:
            # Merge top-level keys like strategy with 'config' keys
            flat = config.copy()
            flat.update(config["config"])
            return SplittingConfig(**flat)
        return SplittingConfig(**config)

    def _parse_preprocessing_config(
        self, config: Dict[str, Any]
    ) -> PreprocessingConfig:
        return PreprocessingConfig(**config)

    def _parse_output_config(self, config: Dict[str, Any]) -> OutputConfig:
        return OutputConfig(**config)

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            return datetime.fromisoformat(str(date_str))
        except ValueError:
            return None

    # =========================================================================
    # Split Files
    # =========================================================================

    def get_scenario_splits(
        self,
        scenario_id: str,
        user_id: str,
    ) -> List[Dict[str, Any]]:
        """Get all split files for a scenario."""
        # Permission check via get_scenario
        self.get_scenario(scenario_id, user_id)

        splits = self.split_repo.find_by_scenario(scenario_id)
        return [self._serialize_split(s) for s in splits]

    def _serialize_split(self, split: TrainingDatasetSplit) -> Dict[str, Any]:
        """Serialize split for API response."""
        return {
            "id": str(split.id),
            "scenario_id": str(split.scenario_id),
            "split_type": split.split_type,
            "record_count": split.record_count,
            "feature_count": split.feature_count,
            "class_distribution": split.class_distribution,
            "group_distribution": split.group_distribution,
            "file_path": split.file_path,
            "file_size_bytes": split.file_size_bytes,
            "file_format": split.file_format,
            "generated_at": (
                split.generated_at.isoformat() if split.generated_at else None
            ),
            "generation_duration_seconds": split.generation_duration_seconds,
        }

    def get_split_by_id(
        self,
        scenario_id: str,
        split_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """Get a specific split file by ID."""
        # Permission check
        self.get_scenario(scenario_id, user_id)

        split = self.split_repo.find_by_id(split_id)
        if not split or str(split.scenario_id) != scenario_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Split {split_id} not found for scenario {scenario_id}",
            )
        return self._serialize_split(split)

    # =========================================================================
    # Build Listing Endpoints
    # =========================================================================

    def get_ingestion_builds(
        self,
        scenario_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        status_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List ingestion builds for a scenario (Phase 1).

        Returns TrainingIngestionBuild records with resource status.
        """
        # Permission check
        self.get_scenario(scenario_id, user_id)

        from app.entities.training_ingestion_build import IngestionStatus

        # Convert status filter to enum
        status_enum = None
        if status_filter:
            try:
                status_enum = IngestionStatus(status_filter)
            except ValueError:
                pass

        builds, total = self.ingestion_build_repo.find_by_scenario(
            scenario_id=scenario_id,
            status_filter=status_enum,
            skip=skip,
            limit=limit,
        )

        items = []
        for build in builds:
            items.append(
                {
                    "id": str(build.id),
                    "ci_run_id": build.ci_run_id or "",
                    "commit_sha": build.commit_sha or "",
                    "repo_full_name": build.repo_full_name or "",
                    "status": (
                        build.status.value
                        if hasattr(build.status, "value")
                        else build.status
                    ),
                    "resource_status": build.resource_status or {},
                    "required_resources": build.required_resources or [],
                    "ingestion_error": build.ingestion_error,
                    "created_at": (
                        build.created_at.isoformat() if build.created_at else None
                    ),
                    "ingested_at": (
                        build.ingested_at.isoformat() if build.ingested_at else None
                    ),
                }
            )

        return {
            "items": items,
            "total": total,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "size": limit,
        }

    def get_enrichment_build_detail(
        self,
        scenario_id: str,
        build_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Get detailed view of an enrichment build.

        Returns:
            - raw_build_run
            - enrichment_build
            - audit_log (if available)
        """
        from app.repositories.feature_audit_log import FeatureAuditLogRepository

        # Permission check
        self.get_scenario(scenario_id, user_id)

        build = self.enrichment_build_repo.find_by_id(build_id)
        if not build:
            raise HTTPException(status_code=404, detail="Enrichment build not found")

        # Get raw build
        raw_build = None
        if build.raw_build_run_id:
            raw_build = self.raw_build_run_repo.find_by_id(build.raw_build_run_id)

        # Get audit log
        audit_repo = FeatureAuditLogRepository(self.db)
        audit_log = audit_repo.find_by_enrichment_build(build_id)

        return {
            "enrichment_build": {
                "id": str(build.id),
                "raw_build_run_id": (
                    str(build.raw_build_run_id) if build.raw_build_run_id else ""
                ),
                "ci_run_id": build.ci_run_id or "",
                "commit_sha": build.commit_sha or "",
                "repo_full_name": build.repo_full_name or "",
                "extraction_status": (
                    build.extraction_status.value
                    if hasattr(build.extraction_status, "value")
                    else build.extraction_status
                ),
                "extraction_error": build.extraction_error,
                "feature_count": build.feature_count or 0,
                "expected_feature_count": build.expected_feature_count or 0,
                "split_assignment": build.split_assignment,
                "created_at": (
                    build.created_at.isoformat() if build.created_at else None
                ),
                "enriched_at": (
                    build.enriched_at.isoformat() if build.enriched_at else None
                ),
                "features": build.features or {},
                "missing_resources": build.missing_resources or [],
                "skipped_features": build.skipped_features or [],
            },
            "raw_build_run": (
                {
                    "id": str(raw_build.id),
                    "repo_name": raw_build.repo_name,
                    "branch": raw_build.branch,
                    "commit_sha": raw_build.commit_sha,
                    "ci_run_id": raw_build.ci_run_id,
                    "provider": raw_build.provider,
                    "web_url": raw_build.web_url,
                    "conclusion": (
                        raw_build.conclusion.value
                        if hasattr(raw_build.conclusion, "value")
                        else raw_build.conclusion
                    ),
                    "run_started_at": (
                        raw_build.run_started_at.isoformat()
                        if raw_build.run_started_at
                        else None
                    ),
                }
                if raw_build
                else {}
            ),
            "audit_log": (
                {
                    "id": str(audit_log.id),
                    "duration_ms": audit_log.duration_ms,
                    "nodes_succeeded": audit_log.nodes_succeeded,
                    "nodes_failed": audit_log.nodes_failed,
                    "nodes_skipped": audit_log.nodes_skipped,
                    "errors": audit_log.errors,
                    "warnings": audit_log.warnings,
                    "node_results": [
                        {
                            "node_name": n.node_name,
                            "status": n.status,
                            "duration_ms": n.duration_ms,
                            "features_extracted": n.features_extracted,
                            "resources_used": n.resources_used,
                            "error": n.error,
                            "warning": n.warning,
                            "skip_reason": n.skip_reason,
                            "retry_count": n.retry_count,
                        }
                        for n in audit_log.node_results
                    ],
                }
                if audit_log
                else None
            ),
        }

    def get_enrichment_builds(
        self,
        scenario_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 20,
        extraction_status: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List enrichment builds for a scenario (Phase 2).

        Returns TrainingEnrichmentBuild records with extraction status.
        """
        from app.entities.enums import ExtractionStatus

        # Permission check
        scenario = self.get_scenario(scenario_id, user_id)

        # Convert status filter
        status_enum = None
        if extraction_status:
            try:
                status_enum = ExtractionStatus(extraction_status)
            except ValueError:
                pass

        builds, total = self.enrichment_build_repo.find_by_scenario(
            scenario_id=scenario_id,
            extraction_status=status_enum,
            skip=skip,
            limit=limit,
        )

        # Get expected feature count from scenario
        expected_features = (
            len(scenario.feature_config.dag_features) if scenario.feature_config else 0
        )

        items = []
        for build in builds:
            items.append(
                {
                    "id": str(build.id),
                    "raw_build_run_id": (
                        str(build.raw_build_run_id) if build.raw_build_run_id else ""
                    ),
                    "ci_run_id": build.ci_run_id or "",
                    "commit_sha": build.commit_sha or "",
                    "repo_full_name": build.repo_full_name or "",
                    "extraction_status": (
                        build.extraction_status.value
                        if hasattr(build.extraction_status, "value")
                        else build.extraction_status
                    ),
                    "extraction_error": build.extraction_error,
                    "feature_count": build.feature_count or 0,
                    "expected_feature_count": expected_features,
                    "split_assignment": build.split_assignment,
                    "created_at": (
                        build.created_at.isoformat() if build.created_at else None
                    ),
                    "enriched_at": (
                        build.enriched_at.isoformat() if build.enriched_at else None
                    ),
                }
            )

        return {
            "items": items,
            "total": total,
            "page": (skip // limit) + 1 if limit > 0 else 1,
            "size": limit,
        }

    def get_scan_status(
        self,
        scenario_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Get scan status summary for a scenario.

        Returns counts of scans completed/pending/failed.
        """
        # Permission check
        scenario = self.get_scenario(scenario_id, user_id)

        return {
            "scans_total": scenario.scans_total or 0,
            "scans_completed": scenario.scans_completed or 0,
            "scans_failed": scenario.scans_failed or 0,
            "scans_pending": max(
                0,
                (scenario.scans_total or 0)
                - (scenario.scans_completed or 0)
                - (scenario.scans_failed or 0),
            ),
        }

    # =========================================================================
    # Retry Actions
    # =========================================================================

    def retry_ingestion(
        self,
        scenario_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Retry failed ingestion builds.

        Requeues builds with status FAILED or MISSING_RESOURCE.
        """
        from app.entities.training_ingestion_build import IngestionStatus
        from app.tasks.training_ingestion import reingest_failed_builds

        scenario = self.get_scenario(scenario_id, user_id)

        if scenario.status not in [
            ScenarioStatus.INGESTED,
            ScenarioStatus.PROCESSING,
            ScenarioStatus.PROCESSED,
        ]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot retry ingestion: scenario not in correct state",
            )

        # Count failed builds
        status_counts = self.ingestion_build_repo.count_by_status(scenario_id)
        failed_count = status_counts.get(IngestionStatus.FAILED.value, 0)
        missing_count = status_counts.get(IngestionStatus.MISSING_RESOURCE.value, 0)
        total_retryable = failed_count + missing_count

        if total_retryable == 0:
            return {"message": "No failed builds to retry", "retry_count": 0}

        # Dispatch retry task
        reingest_failed_builds.delay(scenario_id)

        return {
            "message": f"Retrying {total_retryable} failed builds",
            "retry_count": total_retryable,
        }

    def retry_processing(
        self,
        scenario_id: str,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Retry failed processing builds.

        Requeues enrichment builds with status FAILED.
        """
        from app.entities.enums import ExtractionStatus
        from app.tasks.training_processing import reprocess_failed_builds

        scenario = self.get_scenario(scenario_id, user_id)

        if scenario.status not in [ScenarioStatus.PROCESSED, ScenarioStatus.GENERATING]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot retry processing: scenario not in correct state",
            )

        # Count failed builds
        status_counts = self.enrichment_build_repo.count_by_extraction_status(
            scenario_id
        )
        failed_count = status_counts.get(ExtractionStatus.FAILED.value, 0)

        if failed_count == 0:
            return {"message": "No failed builds to retry", "retry_count": 0}

        # Dispatch retry task
        reprocess_failed_builds.delay(scenario_id)

        return {
            "message": f"Retrying {failed_count} failed builds",
            "retry_count": failed_count,
        }
