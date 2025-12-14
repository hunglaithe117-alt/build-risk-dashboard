"""
Feature Registry - Simplified for Hamilton pipeline.

This module handles feature formatting for database storage.
For feature metadata and definitions, see hamilton_features/_metadata.py

With Hamilton DAG, the registry primarily handles:
- Output format conversion (list → "a,b,c" or "a#b#c")
- Feature value preparation for storage
- (Optional) Metadata queries for UI/validation
"""

from enum import Enum
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class OutputFormat(str, Enum):
    """Output format for list features when saving to DB."""

    RAW = "raw"  # Keep as-is (list)
    COMMA_SEPARATED = "comma"  # Join with comma: "a,b,c"
    HASH_SEPARATED = "hash"  # Join with hash: "a#b#c" (for commit SHAs)
    PIPE_SEPARATED = "pipe"  # Join with pipe: "a|b|c"


class FeatureRegistry:
    """
    Simplified registry for feature output formatting.
    
    Primary role: Convert extracted features to DB-compatible format.
    Example: ["commit1", "commit2"] -> "commit1#commit2"
    
    Note: Feature definitions and metadata are in hamilton_features/_metadata.py
    """

    def __init__(self):
        self._output_formats: Dict[str, OutputFormat] = {}

    def set_output_format(self, feature_name: str, format: OutputFormat) -> None:
        """Register output format for a feature."""
        self._output_formats[feature_name] = format

    def get_output_format(self, feature_name: str) -> OutputFormat:
        """Get the output format for a feature."""
        return self._output_formats.get(feature_name, OutputFormat.RAW)

    def format_features_for_storage(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format feature values for storage in DB.
        
        Converts list features to strings based on registered format:
        - RAW: keep as list
        - COMMA_SEPARATED: "a,b,c"
        - HASH_SEPARATED: "a#b#c"
        - PIPE_SEPARATED: "a|b|c"
        
        Args:
            features: Dictionary of extracted features
            
        Returns:
            Dictionary with formatted values ready for DB storage
        """
        result = {}
        for name, value in features.items():
            output_format = self.get_output_format(name)

            if value is None:
                result[name] = None
            elif isinstance(value, list):
                if not value:
                    result[name] = ""
                elif output_format == OutputFormat.HASH_SEPARATED:
                    result[name] = "#".join(str(v) for v in value)
                elif output_format == OutputFormat.COMMA_SEPARATED:
                    result[name] = ",".join(str(v) for v in value)
                elif output_format == OutputFormat.PIPE_SEPARATED:
                    result[name] = "|".join(str(v) for v in value)
                else:
                    # RAW - keep as list
                    result[name] = value
            else:
                result[name] = value

        return result


# Global registry instance
feature_registry = FeatureRegistry()
