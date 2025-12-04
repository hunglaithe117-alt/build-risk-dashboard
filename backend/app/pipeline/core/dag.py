"""
Feature DAG - Directed Acyclic Graph for feature dependencies.

This module builds a DAG from registered feature nodes and provides:
- Topological sorting for execution order
- Parallel execution grouping (nodes at same level)
- Cycle detection
- Dependency validation
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import logging

from app.pipeline.core.registry import FeatureRegistry, FeatureNodeMeta, feature_registry

logger = logging.getLogger(__name__)


@dataclass
class ExecutionLevel:
    """A group of nodes that can be executed in parallel."""
    level: int
    node_names: List[str] = field(default_factory=list)
    
    def __repr__(self) -> str:
        return f"Level {self.level}: {self.node_names}"


class FeatureDAG:
    """
    Directed Acyclic Graph for feature node dependencies.
    
    Builds a dependency graph based on:
    1. Feature dependencies (node A requires feature X which node B provides)
    2. Resource dependencies (checked at runtime, not part of DAG)
    
    Provides topological sorting and parallel execution levels.
    """
    
    def __init__(self, registry: Optional[FeatureRegistry] = None):
        self.registry = registry or feature_registry
        self._graph: Dict[str, Set[str]] = defaultdict(set)  # node -> dependencies
        self._reverse_graph: Dict[str, Set[str]] = defaultdict(set)  # node -> dependents
        self._built = False
    
    def build(self, node_names: Optional[Set[str]] = None) -> "FeatureDAG":
        """
        Build the dependency graph from registry.
        
        Args:
            node_names: Optional set of specific nodes to include.
                       If None, includes all enabled nodes.
        """
        self._graph.clear()
        self._reverse_graph.clear()
        
        # Get nodes to include
        all_nodes = self.registry.get_all(enabled_only=True)
        if node_names:
            nodes = {k: v for k, v in all_nodes.items() if k in node_names}
        else:
            nodes = all_nodes
        
        # Build feature -> provider mapping
        feature_providers = {}
        for name, meta in nodes.items():
            for feature in meta.provides:
                feature_providers[feature] = name
        
        # Build dependency graph
        for name, meta in nodes.items():
            self._graph[name]  # Ensure node exists even with no deps
            
            for required_feature in meta.requires_features:
                provider = feature_providers.get(required_feature)
                if provider and provider != name:
                    self._graph[name].add(provider)
                    self._reverse_graph[provider].add(name)
        
        self._built = True
        
        # Validate
        cycle = self._detect_cycle()
        if cycle:
            raise ValueError(f"Circular dependency detected: {' -> '.join(cycle)}")
        
        return self
    
    def _detect_cycle(self) -> Optional[List[str]]:
        """Detect cycles in the graph using DFS. Returns cycle path if found."""
        WHITE, GRAY, BLACK = 0, 1, 2
        colors = {node: WHITE for node in self._graph}
        parent = {}
        
        def dfs(node: str) -> Optional[str]:
            colors[node] = GRAY
            for dep in self._graph[node]:
                if dep not in colors:
                    continue
                if colors[dep] == GRAY:
                    return dep  # Found cycle
                if colors[dep] == WHITE:
                    parent[dep] = node
                    result = dfs(dep)
                    if result:
                        return result
            colors[node] = BLACK
            return None
        
        for node in self._graph:
            if colors[node] == WHITE:
                cycle_node = dfs(node)
                if cycle_node:
                    # Reconstruct cycle path
                    path = [cycle_node]
                    current = parent.get(cycle_node)
                    while current and current != cycle_node:
                        path.append(current)
                        current = parent.get(current)
                    path.append(cycle_node)
                    return list(reversed(path))
        
        return None
    
    def topological_sort(self) -> List[str]:
        """
        Return nodes in topological order (dependencies before dependents).
        Uses Kahn's algorithm.
        """
        if not self._built:
            self.build()
        
        # Calculate in-degrees
        in_degree = {node: len(deps) for node, deps in self._graph.items()}
        
        # Start with nodes that have no dependencies
        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        result = []
        
        while queue:
            # Sort by priority (higher first) for deterministic ordering
            queue = deque(sorted(queue, key=lambda n: (
                -self.registry.get(n).priority if self.registry.get(n) else 0,
                n  # Alphabetical as tiebreaker
            )))
            
            node = queue.popleft()
            result.append(node)
            
            for dependent in self._reverse_graph[node]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)
        
        if len(result) != len(self._graph):
            missing = set(self._graph.keys()) - set(result)
            raise ValueError(f"Could not resolve all dependencies. Stuck nodes: {missing}")
        
        return result
    
    def get_execution_levels(self) -> List[ExecutionLevel]:
        """
        Group nodes into parallel execution levels.
        
        Nodes at the same level have no dependencies on each other
        and can be executed in parallel.
        """
        if not self._built:
            self.build()
        
        # Calculate node depths (longest path from a root)
        depths: Dict[str, int] = {}
        
        def calculate_depth(node: str) -> int:
            if node in depths:
                return depths[node]
            
            deps = self._graph[node]
            if not deps:
                depths[node] = 0
            else:
                depths[node] = 1 + max(calculate_depth(dep) for dep in deps)
            
            return depths[node]
        
        for node in self._graph:
            calculate_depth(node)
        
        # Group by depth
        level_nodes: Dict[int, List[str]] = defaultdict(list)
        for node, depth in depths.items():
            level_nodes[depth].append(node)
        
        # Sort nodes within each level by priority
        levels = []
        for level_num in sorted(level_nodes.keys()):
            nodes = sorted(level_nodes[level_num], key=lambda n: (
                -self.registry.get(n).priority if self.registry.get(n) else 0,
                n
            ))
            levels.append(ExecutionLevel(level=level_num, node_names=nodes))
        
        return levels
    
    def get_dependencies(self, node_name: str) -> Set[str]:
        """Get direct dependencies of a node."""
        return self._graph.get(node_name, set())
    
    def get_dependents(self, node_name: str) -> Set[str]:
        """Get nodes that depend on this node."""
        return self._reverse_graph.get(node_name, set())
    
    def get_all_dependencies(self, node_name: str) -> Set[str]:
        """Get all transitive dependencies of a node."""
        result = set()
        queue = deque([node_name])
        
        while queue:
            current = queue.popleft()
            for dep in self._graph.get(current, set()):
                if dep not in result:
                    result.add(dep)
                    queue.append(dep)
        
        return result
    
    def visualize(self) -> str:
        """Generate ASCII visualization of the DAG."""
        if not self._built:
            self.build()
        
        levels = self.get_execution_levels()
        lines = ["Feature DAG Execution Plan:", "=" * 40]
        
        for level in levels:
            lines.append(f"\nLevel {level.level}:")
            for node_name in level.node_names:
                meta = self.registry.get(node_name)
                deps = self._graph.get(node_name, set())
                provides = meta.provides if meta else set()
                
                lines.append(f"  [{node_name}]")
                if deps:
                    lines.append(f"    ← requires: {', '.join(sorted(deps))}")
                if provides:
                    lines.append(f"    → provides: {', '.join(sorted(provides))}")
        
        return "\n".join(lines)
