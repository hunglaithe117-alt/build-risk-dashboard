"""
PipelineContext - Unified context for scan and enrichment pipelines.

Provides a single abstraction to work with either:
- Model Pipeline (Repository processing)
- Training Scenario Pipeline (TrainingScenario)

Auto-detection determines the correct pipeline type from context_id.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.database import Database

logger = logging.getLogger(__name__)


class PipelineType(str, Enum):
    """Supported pipeline types."""

    MODEL_PIPELINE = "model_pipeline"
    TRAINING_SCENARIO = "training_scenario"


@dataclass
class PipelineContext:
    """
    Unified context for pipeline operations.

    Provides common interface for operations that work across
    Model Pipeline and Training Scenario pipelines.
    """

    pipeline_type: PipelineType
    context_id: str  # repo_id for model, scenario_id for training
    db: Database

    @classmethod
    def detect(cls, db: Database, context_id: str) -> Optional["PipelineContext"]:
        """
        Auto-detect pipeline type from context_id.

        Checks MongoDB collections to determine if the ID belongs to
        a Repository (model pipeline) or TrainingScenario.

        Args:
            db: MongoDB database instance
            context_id: The ID to detect (repo_id or scenario_id)

        Returns:
            PipelineContext if found, None if context_id not found in either collection.
        """
        try:
            oid = ObjectId(context_id)
        except InvalidId:
            logger.warning(f"Invalid ObjectId for context detection: {context_id}")
            return None

        # Check TrainingScenario collection first (new primary pipeline)
        scenario_doc = db.training_scenarios.find_one({"_id": oid}, {"_id": 1})
        if scenario_doc:
            return cls(
                pipeline_type=PipelineType.TRAINING_SCENARIO,
                context_id=context_id,
                db=db,
            )

        # Check Repository collection (model pipeline)
        repo_doc = db.repositories.find_one({"_id": oid}, {"_id": 1})
        if repo_doc:
            return cls(
                pipeline_type=PipelineType.MODEL_PIPELINE,
                context_id=context_id,
                db=db,
            )

        logger.warning(
            f"Context {context_id} not found in TrainingScenario or Repository"
        )
        return None

    def get_enrichment_build_repo(self):
        """
        Get the appropriate enrichment build repository for this pipeline.

        Returns:
            TrainingEnrichmentBuildRepository or ModelEnrichmentBuildRepository
        """
        if self.pipeline_type == PipelineType.TRAINING_SCENARIO:
            from app.repositories.training_enrichment_build import (
                TrainingEnrichmentBuildRepository,
            )

            return TrainingEnrichmentBuildRepository(self.db)
        else:
            # Model pipeline uses BuildRun for predictions, not enrichment builds
            # Return None as model pipeline doesn't have enrichment builds
            return None

    def backfill_scan_metrics_by_commit(
        self,
        commit_sha: str,
        scan_features: Dict[str, Any],
        prefix: str = "trivy_",
    ) -> int:
        """
        Backfill scan metrics to FeatureVectors for all builds matching commit.

        Delegates to the appropriate repository method based on pipeline type.

        Args:
            commit_sha: Git commit SHA to match
            scan_features: Dict of metrics to add (e.g., {"vuln_total": 5})
            prefix: Feature prefix ('trivy_' or 'sonar_')

        Returns:
            Number of FeatureVector documents updated.
        """
        if self.pipeline_type == PipelineType.TRAINING_SCENARIO:
            enrichment_build_repo = self.get_enrichment_build_repo()
            return enrichment_build_repo.backfill_by_commit_in_scenario(
                scenario_id=ObjectId(self.context_id),
                commit_sha=commit_sha,
                scan_features=scan_features,
                prefix=prefix,
            )
        else:
            # Model pipeline doesn't use enrichment builds for backfill
            logger.warning("Model pipeline does not support scan backfill")
            return 0

    def increment_scans_completed(self) -> bool:
        """Increment scans_completed counter for this context."""
        from app.tasks.shared.scan_context_helpers import increment_scan_completed

        return increment_scan_completed(self.db, self.context_id)

    def increment_scans_failed(self) -> bool:
        """Increment scans_failed counter for this context."""
        from app.tasks.shared.scan_context_helpers import increment_scan_failed

        return increment_scan_failed(self.db, self.context_id)

    def check_and_mark_scans_completed(self) -> bool:
        """
        Check if all scans are complete and mark scan_extraction_completed.

        Returns:
            True if all scans now complete, False if still pending.
        """
        from app.tasks.shared.scan_context_helpers import check_and_mark_scans_completed

        return check_and_mark_scans_completed(self.db, self.context_id)

    def check_and_notify_completed(self) -> bool:
        """
        Check if processing is fully complete and send notification if needed.

        For TrainingScenario: checks features + scans complete, sends notification.
        For Model Pipeline: checks processing complete, logs completion.

        Returns:
            True if notification was sent/logged, False if still pending.
        """
        if self.pipeline_type == PipelineType.TRAINING_SCENARIO:
            from app.services.notification_service import (
                check_and_notify_scenario_completed,
            )

            return check_and_notify_scenario_completed(
                db=self.db, scenario_id=self.context_id
            )
        else:
            # Model pipeline has its own notification flow
            logger.info(f"Model pipeline {self.context_id} completion check skipped")
            return False
