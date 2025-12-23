"""Feature service for DAG visualization and metadata queries."""

import inspect
import logging
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException

from app.tasks.pipeline.constants import DEFAULT_FEATURES, HAMILTON_MODULES
from app.tasks.pipeline.shared.resources import FeatureResource

logger = logging.getLogger(__name__)

# Input resources derived from FeatureResource enum (source of truth)
# These are passed as inputs to Hamilton, not computed features
# Also includes Hamilton parameter name aliases (e.g., github_client for github_api)
INPUT_RESOURCES = {r.value for r in FeatureResource} | {"github_client"}


class FeatureService:
    """Service for managing feature definitions from Hamilton DAG."""

    def __init__(self):
        """Initialize the service."""
        self._feature_modules = HAMILTON_MODULES
        self._feature_info_cache: Optional[Dict[str, Dict[str, Any]]] = None
        self._metadata_registry_cache: Optional[Dict[str, Dict[str, Any]]] = None

    def _build_pipeline_for_dag_only(self) -> Any:
        """Build Hamilton driver without requiring db parameter."""
        from hamilton import driver

        return driver.Builder().with_modules(*self._feature_modules).build()

    def _build_feature_to_module_mapping(self) -> tuple[Dict[str, str], Set[str]]:
        """Build mapping from feature name to module name by introspection.

        Also handles @extract_fields decorator by mapping extracted field names
        back to the parent function's module.

        Returns:
            Tuple of (mapping dict, set of parent function names with @extract_fields)
        """
        mapping: Dict[str, str] = {}
        extract_field_parents: Set[str] = set()

        for module in self._feature_modules:
            # Extract extractor name from module name (e.g., git_features -> git)
            module_name = module.__name__.split(".")[-1]  # e.g., "git_features"
            extractor_name = module_name.replace("_features", "")  # e.g., "git"

            # Get all functions defined in this module
            for name, obj in inspect.getmembers(module):
                if inspect.isfunction(obj) and not name.startswith("_"):
                    # Check if this function is defined in this module (not imported)
                    try:
                        if obj.__module__ == module.__name__:
                            mapping[name] = extractor_name

                            # Check for @extract_fields decorator
                            # Hamilton stores extract_fields info in func.transform attribute
                            transforms = getattr(obj, "transform", [])
                            for t in transforms:
                                if hasattr(t, "fields") and isinstance(t.fields, dict):
                                    # Mark this parent function for exclusion
                                    extract_field_parents.add(name)
                                    # Map each extracted field to this extractor
                                    for field_name in t.fields.keys():
                                        mapping[field_name] = extractor_name
                    except Exception as e:
                        logger.warning(f"Error inspecting member '{name}': {e}")

        return mapping, extract_field_parents

    def _extract_feature_info(self) -> Dict[str, Dict[str, Any]]:
        """Extract metadata about all features from Hamilton driver."""
        if self._feature_info_cache:
            return self._feature_info_cache

        driver = self._build_pipeline_for_dag_only()

        # Build feature -> module mapping and get parent functions to exclude
        feature_to_module, extract_field_parents = self._build_feature_to_module_mapping()

        # Get all available variables (features) and their upstream dependencies
        all_variables = {v.name for v in driver.list_available_variables()}

        feature_info: Dict[str, Dict[str, Any]] = {}

        for var_name in all_variables:
            if var_name.startswith("_"):
                continue

            # Skip input resources (not actual features)
            # Uses module-level INPUT_RESOURCES derived from FeatureResource enum
            if var_name in INPUT_RESOURCES:
                continue

            # Skip parent functions with @extract_fields (their fields are included separately)
            if var_name in extract_field_parents:
                continue

            # Determine extractor node from module mapping (source of truth)
            extractor = feature_to_module.get(var_name)
            if not extractor:
                # Feature not found in any module - log warning and skip
                logger.warning(
                    f"Feature '{var_name}' not found in module mapping. "
                    f"Ensure it's defined in one of HAMILTON_MODULES or is an extracted field."
                )
                continue

            try:
                # Get upstream dependencies for this variable
                upstream_nodes = driver.what_is_upstream_of(var_name)
                # Convert HamiltonNode objects to names
                depends_on = [
                    n.name if hasattr(n, "name") else str(n)
                    for n in upstream_nodes
                    if (n.name if hasattr(n, "name") else str(n)) != var_name
                ]

                # Try to get docstring
                doc = ""
                if var_name in feature_to_module:
                    # Find the function in the module
                    for module in self._feature_modules:
                        if hasattr(module, var_name):
                            obj = getattr(module, var_name)
                            if inspect.isfunction(obj) or callable(obj):
                                doc = (obj.__doc__ or "").strip()
                                break

                description = doc.split("\n")[0] if doc else var_name

                feature_info[var_name] = {
                    "name": var_name,
                    "display_name": var_name.replace("_", " ").title(),
                    "description": description,
                    "depends_on": depends_on,
                    "extractor_node": extractor,
                    "category": "feature",
                    "source": extractor,
                    "data_type": "any",
                    "is_active": True,
                }
            except Exception as e:
                logger.debug(f"Warning extracting {var_name}: {e}")
                # Add with no dependencies as fallback
                feature_info[var_name] = {
                    "name": var_name,
                    "display_name": var_name.replace("_", " ").title(),
                    "description": var_name,
                    "depends_on": [],
                    "extractor_node": extractor,
                    "category": "feature",
                    "source": extractor,
                    "data_type": "any",
                    "is_active": True,
                }

        self._feature_info_cache = feature_info
        return feature_info

    def get_feature_dag(self, selected_features: Optional[List[str]] = None) -> Dict:
        """Build the Feature DAG structure for visualization."""
        driver = self._build_pipeline_for_dag_only()

        # Get all available features from Hamilton
        # Uses module-level INPUT_RESOURCES derived from FeatureResource enum
        all_variables = {v.name for v in driver.list_available_variables()}
        all_features = {
            f
            for f in all_variables
            if not f.startswith("_") and f not in DEFAULT_FEATURES and f not in INPUT_RESOURCES
        }

        # Get feature info
        feature_info = self._extract_feature_info()

        # Build feature to node mapping
        feature_to_node: Dict[str, str] = {}
        node_features: Dict[str, List[str]] = defaultdict(list)
        node_depends_on_resources: Dict[str, Set[str]] = defaultdict(set)

        for feat_name in all_features:
            if feat_name not in feature_info:
                continue
            info = feature_info[feat_name]
            node_name = info["extractor_node"]
            feature_to_node[feat_name] = node_name
            node_features[node_name].append(feat_name)

            # Identify resource dependencies (parameters that aren't features)
            for dep in info["depends_on"]:
                if dep in INPUT_RESOURCES:
                    node_depends_on_resources[node_name].add(dep)
                elif dep not in all_features:
                    # Other non-feature dependencies (could be intermediate)
                    pass

        # Filter if specific features requested (include dependencies)
        if selected_features:
            to_include_features: Set[str] = set()
            queue = deque(selected_features)

            while queue:
                feat_name = queue.popleft()
                if feat_name in to_include_features or feat_name not in feature_to_node:
                    continue

                to_include_features.add(feat_name)
                info = feature_info.get(feat_name)
                if info:
                    # Add feature dependencies
                    for dep in info["depends_on"]:
                        if dep in all_features and dep not in to_include_features:
                            queue.append(dep)

            # Filter nodes
            node_features = {
                k: [f for f in v if f in to_include_features]
                for k, v in node_features.items()
                if any(f in to_include_features for f in v)
            }

        # Build node dependency graph
        node_deps: Dict[str, Set[str]] = defaultdict(set)
        for node_name, features in node_features.items():
            for feat in features:
                info = feature_info.get(feat)
                if info:
                    for dep in info["depends_on"]:
                        if dep in feature_to_node:
                            dep_node = feature_to_node[dep]
                            if dep_node != node_name and dep_node in node_features:
                                node_deps[node_name].add(dep_node)

        # Calculate execution levels (topological sort)
        levels_map: Dict[str, int] = {}
        computing: Set[str] = set()  # Track nodes in current recursion stack

        def calc_level(node: str) -> int:
            if node in levels_map:
                return levels_map[node]
            # Cycle detection: if node is already being computed, break cycle
            if node in computing:
                logger.warning(f"Circular dependency detected at node: {node}")
                return 0
            computing.add(node)
            deps = node_deps.get(node, set())
            if not deps:
                levels_map[node] = 0
            else:
                max_dep_level = max((calc_level(d) for d in deps if d in node_features), default=-1)
                levels_map[node] = max_dep_level + 1
            computing.discard(node)
            return levels_map[node]

        for node in node_features:
            calc_level(node)

        # Group nodes by level
        level_nodes: Dict[int, List[str]] = defaultdict(list)
        for node, level in levels_map.items():
            level_nodes[level].append(node)

        execution_levels = [
            {"level": lvl, "nodes": sorted(nodes)} for lvl, nodes in sorted(level_nodes.items())
        ]

        # Collect all unique resources
        all_resources = set()
        for node_name in node_features:
            all_resources.update(node_depends_on_resources.get(node_name, set()))

        # Build response nodes
        dag_nodes = []

        # Add resource nodes (level -1)
        for res in sorted(all_resources):
            dag_nodes.append(
                {
                    "id": res,
                    "type": "resource",
                    "label": res.replace("_", " ").title(),
                    "features": [],
                    "feature_count": 0,
                    "requires_resources": [],
                    "requires_features": [],
                    "level": -1,
                }
            )

        # Add extractor nodes
        for node_name in sorted(node_features.keys()):
            features = node_features[node_name]
            node_feature_deps = set()

            for feat in features:
                info = feature_info.get(feat)
                if info:
                    for dep in info["depends_on"]:
                        if dep in all_features:
                            node_feature_deps.add(dep)

            dag_nodes.append(
                {
                    "id": node_name,
                    "type": "extractor",
                    "label": node_name.replace("_", " ").title(),
                    "features": sorted(features),
                    "feature_count": len(features),
                    "requires_resources": sorted(node_depends_on_resources.get(node_name, set())),
                    "requires_features": sorted(node_feature_deps),
                    "level": levels_map.get(node_name, 0),
                }
            )

        # Build edges
        edges = []
        edge_id = 0

        # Resource dependency edges
        for node_name in node_features:
            for res in node_depends_on_resources.get(node_name, set()):
                edges.append(
                    {
                        "id": f"edge_{edge_id}",
                        "source": res,
                        "target": node_name,
                        "type": "resource_dependency",
                    }
                )
                edge_id += 1

        # Feature dependency edges (between nodes)
        for node_name, deps in node_deps.items():
            for dep_node in sorted(deps):
                edges.append(
                    {
                        "id": f"edge_{edge_id}",
                        "source": dep_node,
                        "target": node_name,
                        "type": "feature_dependency",
                    }
                )
                edge_id += 1

        return {
            "nodes": dag_nodes,
            "edges": edges,
            "execution_levels": execution_levels,
            "total_features": sum(len(f) for f in node_features.values()),
            "total_nodes": len(node_features),
        }

    def get_features_by_node(self) -> Dict:
        """Get features grouped by extractor node."""
        feature_info = self._extract_feature_info()
        features = [
            (name, info) for name, info in feature_info.items() if name not in DEFAULT_FEATURES
        ]

        by_node: Dict[str, List[Dict]] = defaultdict(list)

        for feat_name, info in features:
            node = info["extractor_node"]
            by_node[node].append(
                {
                    "name": feat_name,
                    "display_name": info["display_name"],
                    "description": info["description"],
                    "data_type": info["data_type"],
                    "is_active": info["is_active"],
                    "depends_on_features": [d for d in info["depends_on"] if d in feature_info],
                    "depends_on_resources": [
                        d for d in info["depends_on"] if d not in feature_info
                    ],
                }
            )

        result = {}
        for node_name, features_list in by_node.items():
            result[node_name] = {
                "name": node_name,
                "display_name": node_name.replace("_", " ").title(),
                "description": self._get_node_description(node_name),
                "group": self._get_node_group(node_name),
                "is_configured": True,
                "requires_resources": self._get_node_resources(node_name),
                "features": sorted(features_list, key=lambda x: x["name"]),
                "feature_count": len(features_list),
            }

        return {"nodes": result}

    def _get_node_description(self, node_name: str) -> str:
        """Get description for a node."""
        descriptions = {
            "build": "Build/workflow metadata features",
            "git": "Git commit history and code changes",
            "github": "GitHub-specific metrics and discussions",
            "repo": "Repository metadata and metrics",
        }
        return descriptions.get(node_name, f"{node_name} features")

    def _get_node_group(self, node_name: str) -> str:
        """Get group for a node."""
        groups = {
            "build": "workflow",
            "git": "code_analysis",
            "github": "collaboration",
            "repo": "repository",
        }
        return groups.get(node_name, "other")

    def _get_node_resources(self, node_name: str) -> List[str]:
        """Get resources required by a node."""
        feature_info = self._extract_feature_info()
        resources = set()

        for feat_name, info in feature_info.items():
            if info["extractor_node"] == node_name:
                for dep in info["depends_on"]:
                    if dep not in feature_info:
                        resources.add(dep)

        return sorted(resources)

    def list_features(
        self,
        category: Optional[str] = None,
        source: Optional[str] = None,
        extractor_node: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict]:
        """List all feature definitions with optional filters."""
        feature_info = self._extract_feature_info()
        features = [info for name, info in feature_info.items() if name not in DEFAULT_FEATURES]

        if category:
            features = [f for f in features if f["category"] == category]
        if source:
            features = [f for f in features if f["source"] == source]
        if extractor_node:
            features = [f for f in features if f["extractor_node"] == extractor_node]
        if is_active is not None:
            features = [f for f in features if f["is_active"] == is_active]

        return features

    def get_feature(self, feature_name: str) -> Dict:
        """Get a specific feature by name."""
        feature_info = self._extract_feature_info()
        if feature_name not in feature_info:
            raise HTTPException(status_code=404, detail=f"Feature '{feature_name}' not found")
        return feature_info[feature_name]

    def get_feature_summary(self) -> Dict:
        """Get summary statistics about available features."""
        feature_info = self._extract_feature_info()
        features = [info for name, info in feature_info.items() if name not in DEFAULT_FEATURES]

        by_category: dict = {}
        by_source: dict = {}
        by_node: dict = {}

        for f in features:
            cat = f["category"]
            src = f["source"]
            node = f["extractor_node"]

            by_category[cat] = by_category.get(cat, 0) + 1
            by_source[src] = by_source.get(src, 0) + 1
            by_node[node] = by_node.get(node, 0) + 1

        return {
            "total_features": len(features),
            "active_features": sum(1 for f in features if f["is_active"]),
            "deprecated_features": 0,
            "by_category": by_category,
            "by_source": by_source,
            "by_node": by_node,
        }

    def get_supported_languages(self) -> Dict:
        """Get supported programming languages."""
        return {
            "languages": [
                {
                    "name": "Java",
                    "supported": True,
                    "strategy": "JavaLanguageStrategy",
                },
                {
                    "name": "Python",
                    "supported": True,
                    "strategy": "PythonLanguageStrategy",
                },
                {
                    "name": "JavaScript",
                    "supported": True,
                    "strategy": "JavaScriptLanguageStrategy",
                },
            ]
        }

    def validate_features(self, features: List[str]) -> Dict:
        """Validate if features exist and are available."""
        feature_info = self._extract_feature_info()
        valid = []
        invalid = []
        warnings = []

        for feat_name in features:
            if feat_name in feature_info:
                valid.append(feat_name)
            elif feat_name not in DEFAULT_FEATURES:
                invalid.append(feat_name)

        return {
            "valid": len(invalid) == 0,
            "valid_features": valid,
            "invalid_features": invalid,
            "warnings": warnings,
        }
