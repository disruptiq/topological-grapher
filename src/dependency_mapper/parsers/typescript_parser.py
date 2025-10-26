import json
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from ..models import Edge, Node
from .base import AbstractParser


PRIORITIZED_TSCONFIG_NAMES = [
    "tsconfig.app.json",
    "tsconfig.node.json",
    "tsconfig.json",
]


def _find_tsconfig(start_path: Path) -> Optional[Path]:
    """
    Walks up from a starting path to find a prioritized tsconfig file.
    """
    current_dir = start_path.parent
    while current_dir != current_dir.parent:  # Stop at the root
        for config_name in PRIORITIZED_TSCONFIG_NAMES:
            tsconfig_path = current_dir / config_name
            if tsconfig_path.is_file():
                return tsconfig_path
        current_dir = current_dir.parent
    return None


class TypeScriptParser(AbstractParser):
    def __init__(self, root_path: Path):
        self.root_path = root_path
        # Define the path to the Node.js parser script relative to this project's structure
        self.parser_script_path = Path(__file__).parent.parent / "ts_parser" / "index.js"

    def parse(self, file_path: Path, root_path: Path) -> Tuple[List[Node], List[Edge]]:
        tsconfig_path = _find_tsconfig(file_path)
        if not tsconfig_path:
            logging.warning(f"Could not find a tsconfig.json for {file_path}. Skipping.")
            return [], []

        command = [
            "node",
            str(self.parser_script_path),
            "--filePath",
            str(file_path),
            "--rootPath",
            str(self.root_path),
            "--tsconfigPath",
            str(tsconfig_path),
        ]

        try:
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )

            if process.stderr:
                logging.warning(
                    f"TS parser produced warnings for {file_path}:\n{process.stderr}"
                )

            result = json.loads(process.stdout)
            
            nodes = [Node(**node_data) for node_data in result.get("nodes", [])]
            edges = [Edge(**edge_data) for edge_data in result.get("edges", [])]
            
            # The TS parser returns an array of scope IDs. We need to apply this flag.
            dynamic_scope_ids = set(result.get("dynamicScopeIds", []))
            if dynamic_scope_ids:
                for node in nodes:
                    if node.id in dynamic_scope_ids:
                        node.metadata.contains_dynamic_code = True

            return nodes, edges

        except subprocess.CalledProcessError as e:
            logging.error(
                f"Failed to parse TypeScript file {file_path}.\n"
                f"Command: {' '.join(command)}\n"
                f"Error: {e.stderr}"
            )
            return [], []
        except json.JSONDecodeError as e:
            logging.error(f"Failed to decode JSON from TS parser for {file_path}: {e}")
            return [], []
        except Exception as e:
            logging.error(f"An unexpected error occurred while parsing {file_path}: {e}")
            return [], []
