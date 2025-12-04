"""
Pipeline Executor - Executes the feature DAG.

Supports both synchronous and asynchronous execution modes,
with optional parallelization at each level.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Set, Type

from app.pipeline.core.context import ExecutionContext, FeatureResult, FeatureStatus
from app.pipeline.core.dag import FeatureDAG, ExecutionLevel
from app.pipeline.core.registry import FeatureRegistry, feature_registry

logger = logging.getLogger(__name__)


class PipelineExecutor:
    """
    Executes a feature DAG against an execution context.
    
    Features:
    - Level-by-level execution (respects dependencies)
    - Parallel execution within levels (optional)
    - Error handling and partial failure support
    - Execution timing and metrics
    """
    
    def __init__(
        self,
        registry: Optional[FeatureRegistry] = None,
        max_workers: int = 4,
        fail_fast: bool = False,
        skip_on_dependency_failure: bool = True,
    ):
        """
        Initialize the executor.
        
        Args:
            registry: Feature registry to use
            max_workers: Max parallel workers for level execution
            fail_fast: Stop on first error
            skip_on_dependency_failure: Skip nodes whose dependencies failed
        """
        self.registry = registry or feature_registry
        self.max_workers = max_workers
        self.fail_fast = fail_fast
        self.skip_on_dependency_failure = skip_on_dependency_failure
        self._dag: Optional[FeatureDAG] = None
    
    def execute(
        self,
        context: ExecutionContext,
        node_names: Optional[Set[str]] = None,
        parallel: bool = True,
    ) -> ExecutionContext:
        """
        Execute the feature pipeline synchronously.
        
        Args:
            context: Execution context with initialized resources
            node_names: Specific nodes to execute (None = all enabled)
            parallel: Whether to parallelize level execution
        
        Returns:
            Updated context with extracted features
        """
        # Build DAG
        self._dag = FeatureDAG(self.registry).build(node_names)
        levels = self._dag.get_execution_levels()
        
        logger.info(f"Executing feature pipeline with {len(levels)} levels")
        logger.debug(self._dag.visualize())
        
        failed_nodes: Set[str] = set()
        
        for level in levels:
            if parallel and len(level.node_names) > 1:
                results = self._execute_level_parallel(context, level, failed_nodes)
            else:
                results = self._execute_level_sequential(context, level, failed_nodes)
            
            # Process results
            for result in results:
                context.add_result(result)
                if result.is_failed:
                    failed_nodes.add(result.node_name)
                    if self.fail_fast:
                        logger.error(f"Fail-fast triggered by {result.node_name}")
                        return context
        
        return context
    
    def _execute_level_sequential(
        self,
        context: ExecutionContext,
        level: ExecutionLevel,
        failed_nodes: Set[str],
    ) -> List[FeatureResult]:
        """Execute all nodes in a level sequentially."""
        results = []
        
        for node_name in level.node_names:
            result = self._execute_node(context, node_name, failed_nodes)
            results.append(result)
            
            # Add result to context immediately so subsequent nodes in same level
            # can see features if needed (though they shouldn't depend on each other)
            if result.is_success:
                context.merge_features(result.features)
        
        return results
    
    def _execute_level_parallel(
        self,
        context: ExecutionContext,
        level: ExecutionLevel,
        failed_nodes: Set[str],
    ) -> List[FeatureResult]:
        """Execute all nodes in a level in parallel using threads."""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._execute_node, context, node_name, failed_nodes): node_name
                for node_name in level.node_names
            }
            
            for future in as_completed(futures):
                node_name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(f"Unexpected error in parallel execution of {node_name}: {e}")
                    results.append(FeatureResult(
                        node_name=node_name,
                        status=FeatureStatus.FAILED,
                        error=str(e),
                    ))
        
        return results
    
    def _execute_node(
        self,
        context: ExecutionContext,
        node_name: str,
        failed_nodes: Set[str],
    ) -> FeatureResult:
        """Execute a single feature node."""
        start_time = time.time()
        
        # Check for dependency failures
        if self.skip_on_dependency_failure and self._dag:
            deps = self._dag.get_dependencies(node_name)
            failed_deps = deps & failed_nodes
            if failed_deps:
                logger.warning(
                    f"Skipping {node_name} due to failed dependencies: {failed_deps}"
                )
                return FeatureResult(
                    node_name=node_name,
                    status=FeatureStatus.SKIPPED,
                    warning=f"Dependencies failed: {', '.join(failed_deps)}",
                    duration_ms=(time.time() - start_time) * 1000,
                )
        
        # Get node metadata and instantiate
        meta = self.registry.get(node_name)
        if not meta:
            return FeatureResult(
                node_name=node_name,
                status=FeatureStatus.FAILED,
                error=f"Node '{node_name}' not found in registry",
                duration_ms=(time.time() - start_time) * 1000,
            )
        
        # Check required resources
        for resource_name in meta.requires_resources:
            if not context.has_resource(resource_name):
                return FeatureResult(
                    node_name=node_name,
                    status=FeatureStatus.FAILED,
                    error=f"Required resource '{resource_name}' not available",
                    duration_ms=(time.time() - start_time) * 1000,
                )
        
        # Check required features are available
        for feature_name in meta.requires_features:
            if not context.has_feature(feature_name):
                # Feature might be provided by a node that hasn't run yet
                # This shouldn't happen if DAG is built correctly
                provider = self.registry.get_provider(feature_name)
                if provider and provider in failed_nodes:
                    return FeatureResult(
                        node_name=node_name,
                        status=FeatureStatus.SKIPPED,
                        warning=f"Required feature '{feature_name}' not available (provider '{provider}' failed)",
                        duration_ms=(time.time() - start_time) * 1000,
                    )
        
        try:
            # Instantiate and execute the node
            node_instance = meta.node_class()
            features = node_instance.extract(context)
            
            # Validate output
            if not isinstance(features, dict):
                raise TypeError(f"Expected dict from extract(), got {type(features)}")
            
            # Check if all declared features are provided
            missing_features = meta.provides - set(features.keys())
            warning = None
            if missing_features:
                warning = f"Node did not provide declared features: {missing_features}"
                logger.warning(f"{node_name}: {warning}")
            
            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Executed {node_name} in {duration_ms:.2f}ms, "
                       f"extracted {len(features)} features")
            
            return FeatureResult(
                node_name=node_name,
                status=FeatureStatus.SUCCESS,
                features=features,
                warning=warning,
                duration_ms=duration_ms,
            )
            
        except Exception as e:
            logger.error(f"Failed to execute {node_name}: {e}", exc_info=True)
            return FeatureResult(
                node_name=node_name,
                status=FeatureStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )
    
    async def execute_async(
        self,
        context: ExecutionContext,
        node_names: Optional[Set[str]] = None,
    ) -> ExecutionContext:
        """
        Execute the feature pipeline asynchronously.
        
        Useful when feature nodes have async I/O operations.
        """
        # Build DAG
        self._dag = FeatureDAG(self.registry).build(node_names)
        levels = self._dag.get_execution_levels()
        
        logger.info(f"Executing async feature pipeline with {len(levels)} levels")
        
        failed_nodes: Set[str] = set()
        
        for level in levels:
            # Execute all nodes in level concurrently
            tasks = [
                self._execute_node_async(context, node_name, failed_nodes)
                for node_name in level.node_names
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    # This shouldn't happen as _execute_node_async catches exceptions
                    logger.error(f"Unexpected exception: {result}")
                    continue
                
                context.add_result(result)
                if result.is_failed:
                    failed_nodes.add(result.node_name)
                    if self.fail_fast:
                        return context
        
        return context
    
    async def _execute_node_async(
        self,
        context: ExecutionContext,
        node_name: str,
        failed_nodes: Set[str],
    ) -> FeatureResult:
        """Execute a single node asynchronously."""
        # For now, wrap sync execution in executor
        # Feature nodes can be made async later
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._execute_node,
            context,
            node_name,
            failed_nodes,
        )
