"""Test the AsyncDAGExecutor."""

import pytest
import asyncio
from pipeline.dag_executor import AsyncDAGExecutor


class TestDAGExecutor:
    @pytest.mark.asyncio
    async def test_nodes_execute_in_dependency_order(self):
        """Verify topological execution order."""
        order = []

        async def node_a():
            order.append('a')
            return 'a'

        async def node_b():
            order.append('b')
            return 'b'

        async def node_c():
            order.append('c')
            return 'c'

        dag = AsyncDAGExecutor()
        dag.add_node('a', node_a)
        dag.add_node('b', node_b, depends_on=['a'])
        dag.add_node('c', node_c, depends_on=['b'])
        results = await dag.execute()

        assert results['a'] == 'a'
        assert results['b'] == 'b'
        assert results['c'] == 'c'
        assert order.index('a') < order.index('b')
        assert order.index('b') < order.index('c')

    @pytest.mark.asyncio
    async def test_independent_nodes_run_in_parallel(self):
        """Nodes with no dependency should run concurrently."""
        import time
        start_times = {}

        async def slow_a():
            start_times['a'] = time.time()
            await asyncio.sleep(0.1)
            return 'a'

        async def slow_b():
            start_times['b'] = time.time()
            await asyncio.sleep(0.1)
            return 'b'

        async def depends_on_both():
            return 'c'

        dag = AsyncDAGExecutor()
        dag.add_node('a', slow_a)
        dag.add_node('b', slow_b)
        dag.add_node('c', depends_on_both, depends_on=['a', 'b'])

        t0 = time.time()
        await dag.execute()
        elapsed = time.time() - t0

        # Should take ~0.1s not ~0.2s (parallel execution)
        assert elapsed < 0.18, (
            f"Parallel nodes took {elapsed:.2f}s — expected ~0.1s"
        )
        # Both should have started at roughly the same time
        assert abs(start_times['a'] - start_times['b']) < 0.05

    @pytest.mark.asyncio
    async def test_cycle_detection_raises(self):
        """DAG must reject cycles immediately."""
        dag = AsyncDAGExecutor()
        dag.add_node('a', lambda: None, depends_on=['b'])
        dag.add_node('b', lambda: None, depends_on=['a'])
        with pytest.raises(ValueError, match='Cycle detected'):
            dag._topological_sort()

    @pytest.mark.asyncio
    async def test_failed_node_skips_downstream(self):
        """If a node fails, all downstream nodes are skipped.

        The DAG executor catches exceptions internally and stores them
        in self.errors. Downstream nodes are added to self.skipped.
        """
        async def failing_node():
            raise RuntimeError("intentional failure")

        async def downstream():
            return 'should_not_run'

        dag = AsyncDAGExecutor()
        dag.add_node('fail', failing_node)
        dag.add_node('down', downstream, depends_on=['fail'])

        await dag.execute()

        # The failing node should be in errors
        assert 'fail' in dag.errors
        assert isinstance(dag.errors['fail'], RuntimeError)
        # The downstream node should be in skipped (not executed)
        assert 'down' in dag.skipped
        # The downstream node should NOT be in results
        assert 'down' not in dag.results

    @pytest.mark.asyncio
    async def test_timeout_respected(self):
        """Node exceeding timeout raises TimeoutError.

        The DAG executor catches TimeoutError internally and stores it
        in self.errors instead of re-raising.
        """
        async def slow():
            await asyncio.sleep(10)

        dag = AsyncDAGExecutor()
        dag.add_node('slow', slow, timeout_seconds=1)

        await dag.execute()

        # The slow node should be in errors with a TimeoutError
        assert 'slow' in dag.errors
        assert isinstance(dag.errors['slow'], TimeoutError)