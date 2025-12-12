from collections import defaultdict, deque
from typing import Dict, List, Optional

from fastapi import HTTPException

from app.pipeline.core.registry import feature_registry
from app.pipeline.constants import DEFAULT_FEATURES


class FeatureService:
    """Service for managing feature definitions from code registry."""

    def get_feature_dag(self, selected_features: Optional[List[str]] = None) -> Dict:
        """Build the Feature DAG structure for visualization."""
        all_nodes = feature_registry.get_all(enabled_only=True)

        feature_to_node: dict[str, str] = {}
        node_features: dict[str, list] = defaultdict(list)
        node_resources: dict[str, set] = defaultdict(set)
        node_feature_deps: dict[str, set] = defaultdict(set)

        for node_name, meta in all_nodes.items():
            for feature in meta.provides:
                if feature in DEFAULT_FEATURES:
                    continue
                feature_to_node[feature] = node_name
                node_features[node_name].append(feature)

            for resource in meta.requires_resources:
                node_resources[node_name].add(resource)

            for req_feat in meta.requires_features:
                if req_feat not in DEFAULT_FEATURES:
                    node_feature_deps[node_name].add(req_feat)

        # Filter if specific features requested
        if selected_features:
            to_include_features = set()
            to_include_nodes = set()
            queue = deque(selected_features)

            while queue:
                feat_name = queue.popleft()
                if feat_name in to_include_features or feat_name not in feature_to_node:
                    continue
                to_include_features.add(feat_name)
                node_name = feature_to_node[feat_name]
                to_include_nodes.add(node_name)

                meta = all_nodes.get(node_name)
                if meta:
                    for req_feat in meta.requires_features:
                        if (
                            req_feat not in to_include_features
                            and req_feat in feature_to_node
                        ):
                            queue.append(req_feat)

            node_features = {
                k: [f for f in v if f in to_include_features]
                for k, v in node_features.items()
                if k in to_include_nodes
            }

        # Build node dependency graph
        node_deps: dict[str, set] = defaultdict(set)
        for node_name, deps in node_feature_deps.items():
            if node_name not in node_features:
                continue
            for dep_feat in deps:
                dep_node = feature_to_node.get(dep_feat)
                if dep_node and dep_node != node_name and dep_node in node_features:
                    node_deps[node_name].add(dep_node)

        # Calculate levels
        levels_map: dict[str, int] = {}

        def calc_level(node: str) -> int:
            if node in levels_map:
                return levels_map[node]
            deps = node_deps[node]
            if not deps:
                levels_map[node] = 0
            else:
                levels_map[node] = 1 + max(
                    calc_level(d) for d in deps if d in node_features
                )
            return levels_map[node]

        for node in node_features:
            calc_level(node)

        # Group nodes by level
        level_nodes: dict[int, list] = defaultdict(list)
        for node, level in levels_map.items():
            level_nodes[level].append(node)

        execution_levels = [
            {"level": lvl, "nodes": sorted(nodes)}
            for lvl, nodes in sorted(level_nodes.items())
        ]

        # Collect all unique resources
        all_resources = set()
        for node_name in node_features:
            all_resources.update(node_resources.get(node_name, set()))

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
        for node_name, features in node_features.items():
            dag_nodes.append(
                {
                    "id": node_name,
                    "type": "extractor",
                    "label": node_name.replace("_", " ").title(),
                    "features": sorted(features),
                    "feature_count": len(features),
                    "requires_resources": sorted(node_resources.get(node_name, set())),
                    "requires_features": sorted(
                        node_feature_deps.get(node_name, set())
                    ),
                    "level": levels_map.get(node_name, 0),
                }
            )

        # Build edges
        edges = []
        edge_id = 0

        for node_name in node_features:
            for res in node_resources.get(node_name, set()):
                edges.append(
                    {
                        "id": f"edge_{edge_id}",
                        "source": res,
                        "target": node_name,
                        "type": "resource_dependency",
                    }
                )
                edge_id += 1

        for node_name, deps in node_deps.items():
            for dep_node in deps:
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
        all_features = feature_registry.get_features_with_metadata()
        features = [f for f in all_features if f["name"] not in DEFAULT_FEATURES]

        by_node: dict = defaultdict(list)

        for f in features:
            node = f["extractor_node"]
            by_node[node].append(
                {
                    "name": f["name"],
                    "display_name": f["display_name"],
                    "description": f["description"],
                    "data_type": f["data_type"],
                    "is_active": f["is_active"],
                    "depends_on_features": f["depends_on_features"],
                    "depends_on_resources": f["depends_on_resources"],
                }
            )

        # Get node metadata from registry
        all_nodes = feature_registry.get_all(enabled_only=True)

        result = {}
        for node_name, features_list in by_node.items():
            node_meta = all_nodes.get(node_name)
            group = node_meta.group if node_meta else "other"
            requires_resources = list(node_meta.requires_resources) if node_meta else []

            result[node_name] = {
                "name": node_name,
                "display_name": node_name.replace("_", " ").title(),
                "description": self._get_node_description(node_name),
                "group": group,
                "is_configured": self._check_group_configured(group),
                "requires_resources": requires_resources,
                "features": sorted(features_list, key=lambda x: x["name"]),
                "feature_count": len(features_list),
            }

        return {"nodes": result}

    def _get_node_description(self, node_name: str) -> str:
        """Get description for a node from registry or fallback."""
        # First try to get from registry
        node_meta = feature_registry.get(node_name)
        if node_meta and node_meta.description:
            return node_meta.description

        # Fallback to hardcoded (will be removed once all nodes updated)
        fallback = {
            "git_commit_info": "Commit history and previous build resolution",
            "git_diff_features": "Source and test code changes",
            "file_touch_history": "File modification history",
            "team_membership": "Team size and core contributor info",
            "repo_snapshot_features": "Repository metrics and metadata",
            "job_metadata": "CI job IDs and counts",
            "test_log_parser": "Test results from build logs",
            "workflow_metadata": "Workflow run information",
            "github_discussion_features": "PR/Issue comments and discussions",
            "sonar_measures": "SonarQube code quality metrics",
            "trivy_vulnerability_scan": "Security vulnerability scanning",
        }
        return fallback.get(node_name, "")

    def list_features(
        self,
        category: Optional[str] = None,
        source: Optional[str] = None,
        extractor_node: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> List[Dict]:
        """List all feature definitions with optional filters."""
        all_features = feature_registry.get_features_with_metadata()
        features = [f for f in all_features if f["name"] not in DEFAULT_FEATURES]

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
        metadata = feature_registry.get_feature_metadata(feature_name)
        if not metadata:
            raise HTTPException(
                status_code=404, detail=f"Feature '{feature_name}' not found"
            )
        return metadata

    def get_feature_summary(self) -> Dict:
        """Get summary statistics about available features."""
        all_features = feature_registry.get_features_with_metadata()
        features = [f for f in all_features if f["name"] not in DEFAULT_FEATURES]

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
        """Get list of languages supported by the feature extraction pipeline."""
        from app.pipeline.log_parsers import LogParserRegistry
        from app.pipeline.languages import LanguageRegistry

        log_parser_registry = LogParserRegistry()
        log_parser_langs = set(log_parser_registry.get_languages())
        language_strategy_langs = set(LanguageRegistry.get_supported_languages())
        all_supported = log_parser_langs | language_strategy_langs

        return {
            "languages": sorted(all_supported),
            "log_parser_languages": sorted(log_parser_langs),
            "language_strategy_languages": sorted(language_strategy_langs),
        }

    def validate_features(self) -> Dict:
        """Validate feature definitions in code registry."""
        errors = feature_registry.validate()
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": [],
        }

    def _check_group_configured(self, group: str) -> bool:
        """Check if a feature group is configured/available."""
        if group in ("git", "build_log", "repo"):
            return True
        if group == "github":
            from app.config import settings

            return bool(settings.GITHUB_TOKENS)
        if group == "sonar":
            from app.config import settings

            return bool(getattr(settings, "SONAR_HOST_URL", None))
        if group == "security":
            import shutil

            return shutil.which("trivy") is not None
        return True

    def _get_source_display_name(self, source: str) -> str:
        names = {
            "git": "Git Repository",
            "github": "GitHub API",
            "build_log": "Build Logs",
            "sonarqube": "SonarQube",
            "trivy": "Trivy Scanner",
            "repo": "Repository Metadata",
        }
        return names.get(source, source.replace("_", " ").title())

    def _get_source_description(self, source: str) -> str:
        descriptions = {
            "git": "Commit info, diff changes, and team contributions",
            "github": "Pull requests, issues, and GitHub-specific metadata",
            "build_log": "Test results and CI job information",
            "sonarqube": "Code quality metrics and security analysis",
            "trivy": "Container and dependency vulnerability scanning",
            "repo": "Repository metadata and configuration",
        }
        return descriptions.get(source, "")

    def _get_source_icon(self, source: str) -> str:
        icons = {
            "git": "git-branch",
            "github": "github",
            "build_log": "file-text",
            "sonarqube": "shield-check",
            "trivy": "shield-alert",
            "repo": "database",
        }
        return icons.get(source, "box")
