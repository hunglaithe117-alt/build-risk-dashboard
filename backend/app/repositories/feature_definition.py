"""
Feature Definition Repository.

Provides CRUD operations for feature definitions.
"""

from typing import Dict, List, Optional, Set

from pymongo.database import Database

from app.models.entities.feature_definition import (
    FeatureDefinition,
    FeatureCategory,
    FeatureSource,
)
from app.repositories.base import BaseRepository


class FeatureDefinitionRepository(BaseRepository[FeatureDefinition]):
    """Repository for managing feature definitions."""
    
    def __init__(self, db: Database):
        super().__init__(db, "feature_definitions", FeatureDefinition)
        # Create indexes
        self.collection.create_index("name", unique=True)
        self.collection.create_index("category")
        self.collection.create_index("extractor_node")
        self.collection.create_index("is_active")
    
    def find_by_name(self, name: str) -> Optional[FeatureDefinition]:
        """Find a feature by its unique name."""
        return self.find_one({"name": name})
    
    def find_by_category(
        self, 
        category: FeatureCategory,
        active_only: bool = True
    ) -> List[FeatureDefinition]:
        """Find all features in a category."""
        query = {"category": category.value if isinstance(category, FeatureCategory) else category}
        if active_only:
            query["is_active"] = True
        return self.find_many(query, sort=[("name", 1)])
    
    def find_by_source(
        self, 
        source: FeatureSource,
        active_only: bool = True
    ) -> List[FeatureDefinition]:
        """Find all features from a specific source."""
        query = {"source": source.value if isinstance(source, FeatureSource) else source}
        if active_only:
            query["is_active"] = True
        return self.find_many(query, sort=[("name", 1)])
    
    def find_by_extractor(
        self, 
        extractor_node: str,
        active_only: bool = True
    ) -> List[FeatureDefinition]:
        """Find all features extracted by a specific node."""
        query = {"extractor_node": extractor_node}
        if active_only:
            query["is_active"] = True
        return self.find_many(query, sort=[("name", 1)])
    
    def find_active(self) -> List[FeatureDefinition]:
        """Find all active features."""
        return self.find_many({"is_active": True}, sort=[("category", 1), ("name", 1)])
    
    def find_ml_features(self) -> List[FeatureDefinition]:
        """Find all features used in ML models."""
        return self.find_many(
            {"is_active": True, "is_ml_feature": True},
            sort=[("category", 1), ("name", 1)]
        )
    
    def find_deprecated(self) -> List[FeatureDefinition]:
        """Find all deprecated features."""
        return self.find_many({"is_deprecated": True}, sort=[("name", 1)])
    
    def get_dependency_graph(self) -> Dict[str, Set[str]]:
        """
        Build a dependency graph of all features.
        Returns: {feature_name: set of feature names it depends on}
        """
        features = self.find_active()
        return {f.name: set(f.depends_on_features) for f in features}
    
    def get_features_by_node(self) -> Dict[str, List[str]]:
        """
        Group features by their extractor node.
        Returns: {node_name: [feature_names]}
        """
        features = self.find_active()
        result: Dict[str, List[str]] = {}
        for f in features:
            if f.extractor_node not in result:
                result[f.extractor_node] = []
            result[f.extractor_node].append(f.name)
        return result
    
    def upsert_by_name(self, feature: FeatureDefinition) -> FeatureDefinition:
        """Insert or update a feature by its name."""
        existing = self.find_by_name(feature.name)
        if existing:
            updates = feature.model_dump(exclude={"id", "created_at"}, exclude_none=True)
            self.update_one(str(existing.id), updates)
            return self.find_by_name(feature.name)
        return self.insert_one(feature)
    
    def bulk_upsert(self, features: List[FeatureDefinition]) -> int:
        """Bulk upsert features. Returns count of upserted documents."""
        count = 0
        for feature in features:
            self.upsert_by_name(feature)
            count += 1
        return count
    
    def deactivate(self, name: str, reason: str = "") -> bool:
        """Deactivate a feature."""
        feature = self.find_by_name(name)
        if feature:
            self.update_one(str(feature.id), {
                "is_active": False,
                "is_deprecated": True,
                "deprecated_reason": reason,
            })
            return True
        return False
    
    def get_active_feature_names(self) -> Set[str]:
        """Get set of all active feature names."""
        features = self.find_active()
        return {f.name for f in features}
