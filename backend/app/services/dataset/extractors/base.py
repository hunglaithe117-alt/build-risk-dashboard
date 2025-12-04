"""
Base Feature Extractor.

Abstract base class for all feature extractors.
"""

import logging
from abc import ABC, abstractmethod
from typing import Set

from app.services.dataset.context import DatasetExtractionContext

logger = logging.getLogger(__name__)


class BaseFeatureExtractor(ABC):
    """
    Abstract base class for feature extractors.
    
    Each subclass handles extraction of a specific category of features.
    """
    
    # Set of feature names this extractor can provide
    SUPPORTED_FEATURES: Set[str] = set()
    
    @abstractmethod
    def extract(self, ctx: DatasetExtractionContext, features: Set[str]) -> None:
        """
        Extract features and add them to the context.
        
        Args:
            ctx: Extraction context with repo/workflow data
            features: Set of feature names to extract
        """
        pass
    
    def can_extract(self, features: Set[str]) -> bool:
        """
        Check if this extractor can provide any of the requested features.
        
        Args:
            features: Set of requested feature names
            
        Returns:
            True if this extractor supports any of the features
        """
        return bool(features & self.SUPPORTED_FEATURES)
    
    def get_extractable_features(self, features: Set[str]) -> Set[str]:
        """
        Get the subset of features this extractor can extract.
        
        Args:
            features: Set of requested feature names
            
        Returns:
            Set of features this extractor can provide
        """
        return features & self.SUPPORTED_FEATURES
