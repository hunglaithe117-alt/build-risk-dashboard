"""
Feature Definition Aware Registry.

Enhanced registry that integrates with FeatureDefinition documents from MongoDB.
Provides validation and syncing between code-defined nodes and DB-defined features.
"""

import logging
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from app.pipeline.core.registry import FeatureRegistry, FeatureNodeMeta, feature_registry
from app.models.entities.feature_definition import FeatureDefinition

if TYPE_CHECKING:
    from pymongo.database import Database

logger = logging.getLogger(__name__)


class FeatureDefinitionRegistry:
    """
    Registry that combines code-defined FeatureNodes with DB-defined FeatureDefinitions.
    
    Provides:
    - Validation that all node-provided features are defined in DB
    - Filtering of active/inactive features
    - Rich metadata access for each feature
    - Dependency information from both sources
    """
    
    def __init__(self, db: "Database", code_registry: Optional[FeatureRegistry] = None):
        self.db = db
        self.code_registry = code_registry or feature_registry
        self._definitions: Dict[str, FeatureDefinition] = {}
        self._loaded = False
    
    def load(self) -> "FeatureDefinitionRegistry":
        """Load feature definitions from database."""
        from app.repositories.feature_definition import FeatureDefinitionRepository
        
        repo = FeatureDefinitionRepository(self.db)
        features = repo.find_active()
        
        self._definitions = {f.name: f for f in features}
        self._loaded = True
        
        logger.info(f"Loaded {len(self._definitions)} active feature definitions")
        return self
    
    def get_definition(self, name: str) -> Optional[FeatureDefinition]:
        """Get a feature definition by name."""
        if not self._loaded:
            self.load()
        return self._definitions.get(name)
    
    def get_all_definitions(self) -> Dict[str, FeatureDefinition]:
        """Get all active feature definitions."""
        if not self._loaded:
            self.load()
        return self._definitions.copy()
    
    def get_definitions_for_node(self, node_name: str) -> List[FeatureDefinition]:
        """Get all feature definitions extracted by a specific node."""
        if not self._loaded:
            self.load()
        return [f for f in self._definitions.values() if f.extractor_node == node_name]
    
    def get_active_features(self) -> Set[str]:
        """Get names of all active features."""
        if not self._loaded:
            self.load()
        return set(self._definitions.keys())
    
    def get_ml_features(self) -> Set[str]:
        """Get names of features used for ML."""
        if not self._loaded:
            self.load()
        return {name for name, f in self._definitions.items() if f.is_ml_feature}
    
    def is_active(self, feature_name: str) -> bool:
        """Check if a feature is active."""
        if not self._loaded:
            self.load()
        return feature_name in self._definitions
    
    def validate_node_features(self, node_name: str, provided_features: Set[str]) -> List[str]:
        """
        Validate that all features a node claims to provide are defined in DB.
        
        Returns list of error messages (empty if valid).
        """
        if not self._loaded:
            self.load()
        
        errors = []
        for feature_name in provided_features:
            if feature_name not in self._definitions:
                errors.append(
                    f"Node '{node_name}' provides feature '{feature_name}' "
                    "which is not defined in the database"
                )
            elif self._definitions[feature_name].extractor_node != node_name:
                errors.append(
                    f"Node '{node_name}' provides feature '{feature_name}' "
                    f"but DB says it should be extracted by '{self._definitions[feature_name].extractor_node}'"
                )
        
        return errors
    
    def validate_all_nodes(self) -> List[str]:
        """Validate all registered nodes against DB definitions."""
        errors = []
        
        for node_name, meta in self.code_registry.get_all().items():
            node_errors = self.validate_node_features(node_name, meta.provides)
            errors.extend(node_errors)
        
        # Also check for orphan definitions (features in DB but no node provides them)
        if not self._loaded:
            self.load()
        
        all_provided = set()
        for meta in self.code_registry.get_all().values():
            all_provided.update(meta.provides)
        
        for feature_name in self._definitions:
            if feature_name not in all_provided:
                errors.append(
                    f"Feature '{feature_name}' is defined in DB but no registered node provides it"
                )
        
        return errors
    
    def sync_from_nodes(self, update_db: bool = False) -> Dict[str, any]:
        """
        Sync feature definitions from code nodes to database.
        
        Returns summary of sync operation.
        """
        from app.repositories.feature_definition import FeatureDefinitionRepository
        
        repo = FeatureDefinitionRepository(self.db)
        
        summary = {
            "nodes_checked": 0,
            "features_in_code": 0,
            "features_in_db": len(self._definitions) if self._loaded else 0,
            "missing_in_db": [],
            "extra_in_db": [],
        }
        
        all_provided = set()
        for node_name, meta in self.code_registry.get_all().items():
            summary["nodes_checked"] += 1
            all_provided.update(meta.provides)
        
        summary["features_in_code"] = len(all_provided)
        
        # Find features in code but not in DB
        if not self._loaded:
            self.load()
        
        for feature_name in all_provided:
            if feature_name not in self._definitions:
                summary["missing_in_db"].append(feature_name)
        
        # Find features in DB but not in code
        for feature_name in self._definitions:
            if feature_name not in all_provided:
                summary["extra_in_db"].append(feature_name)
        
        return summary
    
    def get_dependency_info(self, feature_name: str) -> Dict[str, any]:
        """Get detailed dependency information for a feature."""
        if not self._loaded:
            self.load()
        
        definition = self._definitions.get(feature_name)
        if not definition:
            return {"error": f"Feature '{feature_name}' not found"}
        
        return {
            "name": feature_name,
            "extractor_node": definition.extractor_node,
            "depends_on_features": definition.depends_on_features,
            "depends_on_resources": definition.depends_on_resources,
            "source": definition.source,
            "category": definition.category,
            "is_ml_feature": definition.is_ml_feature,
            "data_type": definition.data_type,
        }
    
    def get_extraction_order(self) -> List[str]:
        """
        Get features in extraction order based on dependencies.
        
        Uses topological sort on feature dependencies.
        """
        if not self._loaded:
            self.load()
        
        # Build dependency graph
        from collections import deque
        
        graph: Dict[str, Set[str]] = {}
        in_degree: Dict[str, int] = {}
        
        for name, defn in self._definitions.items():
            deps = set(defn.depends_on_features) & set(self._definitions.keys())
            graph[name] = deps
            in_degree[name] = len(deps)
        
        # Kahn's algorithm
        queue = deque([name for name, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            node = queue.popleft()
            result.append(node)
            
            for name, deps in graph.items():
                if node in deps:
                    in_degree[name] -= 1
                    if in_degree[name] == 0:
                        queue.append(name)
        
        return result


def get_definition_registry(db: "Database") -> FeatureDefinitionRegistry:
    """Factory function to create a loaded FeatureDefinitionRegistry."""
    return FeatureDefinitionRegistry(db).load()
