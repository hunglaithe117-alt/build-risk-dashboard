"""
Pipeline Executor - Executes the feature DAG.

Supports both synchronous and asynchronous execution modes,
with optional parallelization at each level.

Enhanced features:
- Retry mechanism with exponential backoff
- Timeout support per node
- Execution metrics tracking
"""

import asyncio
import logging
import signal
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Set, Type

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    RetryError,
)

from app.pipeline.core.context import ExecutionContext, FeatureResult, FeatureStatus
from app.pipeline.core.dag import FeatureDAG, ExecutionLevel
from app.pipeline.core.registry import FeatureRegistry, feature_registry

logger = logging.getLogger(__name__)


# Network-related exceptions that should trigger retry
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,  # Includes network errors
)


class NodeTimeoutError(Exception):
    """Raised when a node execution times out."""
    pass


class PipelineExecutor:
    """
    Executes a feature DAG against an execution context.

    Features:
    - Level-by-level execution (respects dependencies)
    - Parallel execution within levels (optional)
    - Error handling and partial failure support
    - Execution timing and metrics
    - Retry mechanism with exponential backoff
    - Timeout support per node
    """

    def __init__(
        self,
        registry: Optional[FeatureRegistry] = None,
        max_workers: int = 4,
        fail_fast: bool = False,
        skip_on_dependency_failure: bool = True,
        # Retry configuration
        max_retries: int = 3,
        retry_delay: float = 1.0,  # Base delay in seconds
        retry_max_delay: float = 60.0,  # Max delay between retries
        # Timeout configuration
        node_timeout: Optional[float] = 300.0,  # 5 minutes default, None to disable
    ):
        """
        Initialize the executor.

        Args:
            registry: Feature registry to use
            max_workers: Max parallel workers for level execution
            fail_fast: Stop on first error
            skip_on_dependency_failure: Skip nodes whose dependencies failed
            max_retries: Maximum retry attempts for retryable errors
            retry_delay: Base delay between retries (exponential backoff)
            retry_max_delay: Maximum delay between retries
            node_timeout: Timeout in seconds for each node execution
        """
        self.registry = registry or feature_registry
        self.max_workers = max_workers
        self.fail_fast = fail_fast
        self.skip_on_dependency_failure = skip_on_dependency_failure
        self._dag: Optional[FeatureDAG] = None

        # Retry configuration
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.retry_max_delay = retry_max_delay

        # Timeout configuration
        self.node_timeout = node_timeout

        # Metrics tracking
        self._retry_counts: Dict[str, int] = {}


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
        # Build DAG from code registry
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
                executor.submit(
                    self._execute_node, context, node_name, failed_nodes
                ): node_name
                for node_name in level.node_names
            }

            for future in as_completed(futures):
                node_name = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    logger.error(
                        f"Unexpected error in parallel execution of {node_name}: {e}"
                    )
                    results.append(
                        FeatureResult(
                            node_name=node_name,
                            status=FeatureStatus.FAILED,
                            error=str(e),
                        )
                    )

        return results

    def _execute_node(
        self,
        context: ExecutionContext,
        node_name: str,
        failed_nodes: Set[str],
    ) -> FeatureResult:
        """Execute a single feature node with retry and timeout support."""
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

        # Execute with retry and timeout
        retry_count = 0
        last_error: Optional[Exception] = None

        try:
            result = self._execute_node_with_retry(
                context, node_name, meta, start_time
            )
            # Track retry count
            retry_count = self._retry_counts.get(node_name, 0)
            return result

        except RetryError as e:
            # All retries exhausted
            retry_count = self.max_retries
            last_error = e.last_attempt.exception() if e.last_attempt else e
            logger.error(
                f"Node {node_name} failed after {retry_count} retries: {last_error}"
            )
            return FeatureResult(
                node_name=node_name,
                status=FeatureStatus.FAILED,
                error=f"Failed after {retry_count} retries: {last_error}",
                duration_ms=(time.time() - start_time) * 1000,
            )

        except NodeTimeoutError as e:
            logger.error(f"Node {node_name} timed out after {self.node_timeout}s")
            return FeatureResult(
                node_name=node_name,
                status=FeatureStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            logger.error(f"Failed to execute {node_name}: {e}", exc_info=True)
            return FeatureResult(
                node_name=node_name,
                status=FeatureStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start_time) * 1000,
            )

    def _execute_node_with_retry(
        self,
        context: ExecutionContext,
        node_name: str,
        meta: Any,
        start_time: float,
    ) -> FeatureResult:
        """
        Execute node with retry logic using tenacity.
        
        Retries on network-related exceptions with exponential backoff.
        """
        attempt_count = 0

        @retry(
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(
                multiplier=self.retry_delay,
                min=self.retry_delay,
                max=self.retry_max_delay,
            ),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            reraise=True,
        )
        def do_extract():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count > 1:
                logger.info(
                    f"Retrying {node_name} (attempt {attempt_count}/{self.max_retries})"
                )
            return self._do_node_extraction(context, node_name, meta)

        # Execute with optional timeout
        if self.node_timeout:
            features = self._execute_with_timeout(do_extract, node_name)
        else:
            features = do_extract()

        # Track retry attempts
        self._retry_counts[node_name] = attempt_count - 1

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
        retries = self._retry_counts.get(node_name, 0)
        
        log_msg = f"Executed {node_name} in {duration_ms:.2f}ms, extracted {len(features)} features"
        if retries > 0:
            log_msg += f" (after {retries} retries)"
        logger.info(log_msg)

        return FeatureResult(
            node_name=node_name,
            status=FeatureStatus.SUCCESS,
            features=features,
            warning=warning,
            duration_ms=duration_ms,
        )

    def _do_node_extraction(
        self,
        context: ExecutionContext,
        node_name: str,
        meta: Any,
    ) -> Dict[str, Any]:
        """Perform the actual node extraction (no retry/timeout logic here)."""
        node_instance = meta.node_class()
        return node_instance.extract(context)

    def _execute_with_timeout(
        self,
        func: Callable[[], Any],
        node_name: str,
    ) -> Any:
        """
        Execute a function with timeout using ThreadPoolExecutor.
        
        Note: Using ThreadPoolExecutor for timeout instead of signal.alarm
        because signal only works in main thread.
        """
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(func)
            try:
                return future.result(timeout=self.node_timeout)
            except FuturesTimeoutError:
                future.cancel()
                raise NodeTimeoutError(
                    f"Node '{node_name}' execution timed out after {self.node_timeout}s"
                )

    def get_retry_stats(self) -> Dict[str, int]:
        """Get retry counts for all executed nodes."""
        return self._retry_counts.copy()

    def reset_metrics(self) -> None:
        """Reset execution metrics."""
        self._retry_counts.clear()


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
