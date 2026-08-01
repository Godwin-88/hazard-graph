"""HazardGraph — Explicit asyncio DAG executor for the ML pipeline.

Topological sort + asyncio.gather for parallel execution where
dependencies are satisfied. The entire ML pipeline IS a DAG;
this makes it explicit and observable.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class DAGNode:
    """A single node in the pipeline DAG."""

    name: str
    fn: Callable[..., Awaitable]
    depends_on: list[str] = field(default_factory=list)
    timeout_seconds: int = 300


class AsyncDAGExecutor:
    """Executes a DAG of async functions with topological ordering.

    Nodes in the same topological batch run concurrently via asyncio.gather.
    If a node fails, downstream nodes are marked as skipped.
    """

    def __init__(self):
        self.nodes: dict[str, DAGNode] = {}
        self.results: dict[str, Any] = {}
        self.errors: dict[str, Exception] = {}
        self.skipped: set[str] = set()

    def _build_context(self) -> dict[str, Any]:
        """Build a kwargs context mapping completed node results downstream.

        Each completed node's result is exposed as ``{name}_results`` so
        downstream nodes can consume the outputs of their dependencies
        (e.g. a 'scoring' node result becomes ``scoring_results``).
        """
        context: dict[str, Any] = {}
        for name, result in self.results.items():
            context[f"{name}_results"] = result
        return context

    def add_node(
        self,
        name: str,
        fn: Callable[..., Awaitable],
        depends_on: list[str] | None = None,
        timeout_seconds: int = 300,
    ):
        """Register a node in the DAG.

        Args:
            name: Unique node identifier
            fn: Async callable to execute
            depends_on: List of node names this node depends on
            timeout_seconds: Max execution time before TimeoutError
        """
        if name in self.nodes:
            raise ValueError(f"Node '{name}' already registered in DAG")

        self.nodes[name] = DAGNode(
            name=name,
            fn=fn,
            depends_on=depends_on or [],
            timeout_seconds=timeout_seconds,
        )

    def _topological_sort(self) -> list[list[str]]:
        """Returns list of batches. Each batch runs in parallel.

        Batch 0: no dependencies.
        Batch N: depends only on previous batches.

        Raises:
            ValueError: If a cycle is detected in the DAG
        """
        in_degree: dict[str, int] = {
            name: len(node.depends_on)
            for name, node in self.nodes.items()
        }
        batches: list[list[str]] = []
        remaining = set(self.nodes.keys())

        while remaining:
            batch = [n for n in remaining if in_degree[n] == 0]
            if not batch:
                raise ValueError(
                    f"Cycle detected in pipeline DAG — "
                    f"remaining nodes: {sorted(remaining)}. "
                    f"Check dependency definitions to break the cycle."
                )
            batches.append(batch)
            for name in batch:
                remaining.remove(name)
                for other in remaining:
                    if name in self.nodes[other].depends_on:
                        in_degree[other] -= 1

        return batches

    async def execute(self, **kwargs) -> dict[str, Any]:
        """Execute the DAG. Nodes in same batch run concurrently.

        Args:
            **kwargs: Passed to all node functions

        Returns:
            dict[str, Any]: Results for all completed nodes
        """
        if not self.nodes:
            logger.warning("DAG has no nodes — nothing to execute")
            return {}

        batches = self._topological_sort()
        self.results = {}
        self.errors = {}
        self.skipped = set()
        run_kwargs = dict(kwargs)

        total_nodes = len(self.nodes)
        executed_count = 0
        skipped_count = 0

        logger.info(
            "Executing pipeline DAG: %d nodes in %d batches",
            total_nodes,
            len(batches),
        )

        for batch_idx, batch in enumerate(batches):
            runnable = [n for n in batch if n not in self.skipped]
            if not runnable:
                logger.info("Batch %d: all nodes skipped", batch_idx)
                continue

            logger.info(
                "Batch %d: running %d node(s) in parallel: %s",
                batch_idx,
                len(runnable),
                runnable,
            )

            tasks = []
            for name in runnable:
                node = self.nodes[name]
                # Check if any dependency failed
                deps_failed = any(dep in self.errors for dep in node.depends_on)
                if deps_failed:
                    self.skipped.add(name)
                    skipped_count += 1
                    logger.warning(
                        "Skipping '%s' — dependency failed",
                        name,
                    )
                    continue
                tasks.append(self._run_node(name, node, **run_kwargs))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=False)
                executed_count += len(tasks)

            # Expose completed results to downstream batches
            run_kwargs.update(self._build_context())

        logger.info(
            "Pipeline DAG complete: %d executed, %d skipped, %d errors",
            executed_count,
            skipped_count,
            len(self.errors),
        )

        return self.results

    async def _run_node(self, name: str, node: DAGNode, **kwargs):
        """Execute a single DAG node with timeout.

        ``kwargs`` may include results of previously completed nodes
        (exposed as ``{name}_results``) so downstream nodes can consume
        their dependency outputs.
        """
        start = datetime.now(timezone.utc)
        logger.info("Starting node '%s' (timeout=%ds)", name, node.timeout_seconds)

        try:
            result = await asyncio.wait_for(
                node.fn(**kwargs),
                timeout=node.timeout_seconds,
            )
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            self.results[name] = result
            logger.info("Node '%s' completed in %.1fs", name, elapsed)

        except asyncio.TimeoutError:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            err = TimeoutError(
                f"Node '{name}' timed out after {node.timeout_seconds}s "
                f"(took {elapsed:.1f}s before timeout)"
            )
            self.errors[name] = err
            logger.error("Node '%s' timed out after %ds", name, node.timeout_seconds)

        except Exception as exc:
            elapsed = (datetime.now(timezone.utc) - start).total_seconds()
            self.errors[name] = exc
            logger.error(
                "Node '%s' failed after %.1fs: %s",
                name,
                elapsed,
                exc,
            )

    def get_status(self) -> dict:
        """Return current execution status."""
        return {
            "total_nodes": len(self.nodes),
            "completed": len(self.results),
            "errors": len(self.errors),
            "skipped": len(self.skipped),
            "node_names": list(self.nodes.keys()),
            "error_details": {
                name: str(err) for name, err in self.errors.items()
            },
        }