from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class NodeType(str, Enum):
    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    VARIABLE = "variable"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    NAMESPACE = "namespace"


class EdgeType(str, Enum):
    CONTAINS = "contains"
    IMPORTS = "imports"
    CALLS = "calls"
    INHERITS = "inherits"
    IMPLEMENTS = "implements"
    DECORATES = "decorates"
    USES_TYPE = "uses_type"
    USES_VARIABLE = "uses_variable"


class NodeMetadata(BaseModel):
    file_path: Path
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    contains_dynamic_code: bool = False


class Node(BaseModel):
    id: str  # Unique identifier, e.g., "path/to/file.py:MyClass.my_method"
    type: NodeType
    name: str  # The short name, e.g., "my_method"
    metadata: NodeMetadata


class Edge(BaseModel):
    source: str  # ID of the node with the dependency
    target: str  # ID of the node being depended upon
    type: EdgeType
