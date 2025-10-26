from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Tuple

from ..models import Edge, Node


class AbstractParser(ABC):
    @abstractmethod
    def parse(self, file_path: Path, root_path: Path) -> Tuple[List[Node], List[Edge]]:
        """
        Parses a single source file to extract nodes and edges.
        """
        raise NotImplementedError
