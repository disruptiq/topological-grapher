from pathlib import Path
from typing import List, Optional

import networkx as nx
from networkx.exception import NetworkXUnfeasible

from .graph_builder import GraphBuilder
from .orchestrator import run_parallel_parsing
from .utils import check_command_installed
from .walkers import get_file_walker


TS_JS_EXTENSIONS = {".ts", ".js", ".tsx", ".jsx"}


class CircularDependencyError(Exception):
    """Custom exception for circular dependencies."""
    pass


def generate_graph(root_path: Path, num_workers: Optional[int] = None) -> nx.DiGraph:
    """
    Analyzes a codebase directory and generates a dependency graph in parallel.

    Args:
        root_path: The root directory of the codebase to analyze.
        num_workers: The number of parallel processes to use. Defaults to the number of CPU cores.

    Returns:
        A networkx.DiGraph representing the dependency graph.
    """
    walker = get_file_walker(root_path)
    file_paths = list(walker.walk())

    # Check if node is installed, but only if there are TS/JS files to parse.
    if any(p.suffix in TS_JS_EXTENSIONS for p in file_paths):
        check_command_installed("node")

    # Delegate all parsing work to the parallel orchestrator.
    all_nodes, all_edges = run_parallel_parsing(file_paths, root_path, num_workers)
    
    builder = GraphBuilder()
    return builder.build(all_nodes, all_edges)


def get_analysis_layers(graph: nx.DiGraph) -> List[List[str]]:
    """
    Performs a topological sort on the graph to determine analysis layers.

    Args:
        graph: The dependency graph.

    Returns:
        A list of lists, where each inner list represents a layer of nodes
        that can be analyzed in parallel.

    Raises:
        CircularDependencyError: If a cycle is detected in the graph.
    """
    try:
        # The topological_generations function returns layers directly.
        return list(nx.topological_generations(graph))
    except NetworkXUnfeasible as e:
        # If the sort fails, find and report the cycle.
        cycle = nx.find_cycle(graph)
        cycle_str = " -> ".join([f"'{node}'" for node, _ in cycle]) + f" -> '{cycle[0][0]}'"
        raise CircularDependencyError(f"A circular dependency was detected: {cycle_str}") from e
