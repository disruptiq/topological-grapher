import logging
import multiprocessing
import os
import sys
from functools import partial
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .models import Edge, Node
from .parsers.python_parser import PythonParser
from .parsers.typescript_parser import TypeScriptParser


# A mapping from file extensions to their corresponding parser classes.
PARSER_MAPPING = {
    ".py": PythonParser,
    ".ts": TypeScriptParser,
    ".tsx": TypeScriptParser,
    ".js": TypeScriptParser,
    ".jsx": TypeScriptParser,
}


def _parse_file_worker(file_path: Path, root_path: Path) -> Tuple[List[Node], List[Edge]]:
    """
    A top-level function that can be pickled and sent to a worker process.
    It dynamically selects the correct parser based on the file extension.
    """
    parser_class = PARSER_MAPPING.get(file_path.suffix)

    if not parser_class:
        logging.warning(f"No parser found for file type: {file_path.suffix}. Skipping.")
        return [], []

    original_sys_path = sys.path[:]
    try:
        # sys.path modification is only needed for the Python parser.
        if parser_class is PythonParser:
            if str(root_path) not in sys.path:
                sys.path.insert(0, str(root_path))
        
        # Each worker gets its own parser instance.
        parser = parser_class(root_path)
        return parser.parse(file_path, root_path)
    finally:
        sys.path[:] = original_sys_path


def run_parallel_parsing(
    file_paths: Iterable[Path], root_path: Path, num_workers: Optional[int] = None
) -> Tuple[List[Node], List[Edge]]:
    """
    Manages a pool of worker processes to parse files in parallel.
    """
    if num_workers is None:
        num_workers = os.cpu_count()

    all_nodes: List[Node] = []
    all_edges: List[Edge] = []

    # Use functools.partial to "bake in" the root_path argument for the worker.
    worker_func = partial(_parse_file_worker, root_path=root_path)

    with multiprocessing.Pool(processes=num_workers) as pool:
        # Use imap_unordered for efficiency, processing results as they complete.
        results = pool.imap_unordered(worker_func, file_paths)
        
        for nodes, edges in results:
            all_nodes.extend(nodes)
            all_edges.extend(edges)

    return all_nodes, all_edges
