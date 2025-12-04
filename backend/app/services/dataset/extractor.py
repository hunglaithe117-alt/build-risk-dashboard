"""
Dataset Feature Extractor.

Main coordinator for all feature extraction.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pymongo.database import Database

from app.models.entities.imported_repository import ImportedRepository
from app.models.entities.workflow_run import WorkflowRunRaw
from app.services.dataset.context import DatasetExtractionContext, ExtractionStatus
from app.services.dataset.extractors.basic import BasicFeatureExtractor
from app.services.dataset.extractors.log import LogFeatureExtractor
from app.services.dataset.extractors.git import GitFeatureExtractor
from app.services.dataset.extractors.github import GitHubFeatureExtractor

logger = logging.getLogger(__name__)


class DatasetFeatureExtractor:
    """
    Feature extractor for Custom Dataset Builder.
    
    This class coordinates extraction of features from workflow runs
    without using BuildSample or the main pipeline infrastructure.
    
    It delegates to specialized extractors for different feature categories.
    """
    
    def __init__(
        self,
        db: Database,
        source_languages: Optional[List[str]] = None,
        log_dir: Optional[Path] = None,
        repos_dir: Optional[Path] = None,
    ):
        """
        Initialize the dataset extractor.
        
        Args:
            db: MongoDB database instance
            source_languages: List of source languages for the project
            log_dir: Directory where job logs are stored
            repos_dir: Directory where repositories are cloned
        """
        self.db = db
        self.source_languages = source_languages or []
        
        # Storage paths
        self.log_dir = log_dir or Path("../repo-data/job_logs")
        self.repos_dir = repos_dir or Path("../repo-data/repos")
        
        # Initialize extractors
        self._basic_extractor = BasicFeatureExtractor()
        self._log_extractor = LogFeatureExtractor(self.log_dir)
        self._git_extractor = GitFeatureExtractor(self.repos_dir)
        self._github_extractor = GitHubFeatureExtractor()
    
    def extract(
        self,
        repo: ImportedRepository,
        workflow_run: WorkflowRunRaw,
        features_to_extract: Set[str],
    ) -> Dict[str, Any]:
        """
        Extract specified features from a workflow run.
        
        Args:
            repo: Repository entity
            workflow_run: Workflow run data
            features_to_extract: Set of feature names to extract
            
        Returns:
            Dict with status, features, errors, warnings
        """
        # Normalize source languages
        effective_languages = self._normalize_languages(
            self.source_languages or repo.source_languages or []
        )
        
        # Create extraction context
        ctx = DatasetExtractionContext(
            repo=repo,
            workflow_run=workflow_run,
            db=self.db,
            source_languages=effective_languages,
        )
        
        try:
            # Run all extractors
            self._basic_extractor.extract(ctx, features_to_extract)
            
            if self._log_extractor.can_extract(features_to_extract):
                self._log_extractor.extract(ctx, features_to_extract)
            
            if self._git_extractor.can_extract(features_to_extract):
                self._git_extractor.extract(ctx, features_to_extract)
            
            if self._github_extractor.can_extract(features_to_extract):
                self._github_extractor.extract(ctx, features_to_extract)
            
            # Determine status
            status = self._determine_status(ctx)
            
            return {
                "status": status.value,
                "features": ctx.features,
                "errors": ctx.errors,
                "warnings": ctx.warnings,
            }
            
        except Exception as e:
            logger.error(f"Extraction failed for run {workflow_run.workflow_run_id}: {e}")
            return {
                "status": ExtractionStatus.FAILED.value,
                "features": ctx.features,
                "errors": ctx.errors + [str(e)],
                "warnings": ctx.warnings,
            }
    
    def _normalize_languages(self, raw_languages: List) -> List[str]:
        """Convert language values to strings."""
        result: List[str] = []
        for lang in raw_languages:
            if isinstance(lang, str):
                result.append(lang)
            elif hasattr(lang, 'value'):
                result.append(lang.value)
            else:
                result.append(str(lang))
        return result
    
    def _determine_status(self, ctx: DatasetExtractionContext) -> ExtractionStatus:
        """Determine extraction status based on context."""
        if ctx.errors:
            if ctx.features:
                return ExtractionStatus.PARTIAL
            return ExtractionStatus.FAILED
        return ExtractionStatus.SUCCESS
    
    @property
    def supported_features(self) -> Set[str]:
        """Get all features supported by this extractor."""
        return (
            self._basic_extractor.SUPPORTED_FEATURES |
            self._log_extractor.SUPPORTED_FEATURES |
            self._git_extractor.SUPPORTED_FEATURES |
            self._github_extractor.SUPPORTED_FEATURES
        )
