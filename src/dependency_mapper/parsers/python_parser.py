import logging
from pathlib import Path
from typing import List, Tuple

import astroid
from astroid import nodes
from astroid.manager import AstroidManager

from ..models import Edge, EdgeType, Node, NodeMetadata, NodeType
from .base import AbstractParser


DYNAMIC_FUNCTION_NAMES = {"eval", "exec", "getattr", "importlib.import_module"}


def _get_node_id(node: nodes.NodeNG, file_path: Path, root_path: Path) -> str:
    relative_path = file_path.relative_to(root_path).as_posix()
    if isinstance(node, nodes.Module):
        return str(relative_path)
    try:
        return f"{relative_path}__{node.qname()}"
    except AttributeError:
        # Fallback for nodes without qname
        return f"{relative_path}__{node.as_string()}"


class AstroidVisitor:
    def __init__(self, file_path: Path, root_path: Path):
        self.file_path = file_path
        self.root_path = root_path
        self._nodes: List[Node] = []
        self._edges: List[Edge] = []
        self._scope_stack: List[str] = []
        self.dynamic_scope_ids: set[str] = set()

    def visit(self, module: nodes.Module):
        self._visit_recursive(module)
        return self._nodes, self._edges, self.dynamic_scope_ids

    def _visit_recursive(self, node: nodes.NodeNG):
        method_name = f"_visit_{node.__class__.__name__.lower()}"
        visitor_method = getattr(self, method_name, self._default_visit)
        visitor_method(node)

    def _default_visit(self, node: nodes.NodeNG):
        for child in node.get_children():
            self._visit_recursive(child)

    def _add_node(self, node: nodes.NodeNG, node_type: NodeType, name: str):
        node_id = _get_node_id(node, self.file_path, self.root_path)
        relative_file_path = self.file_path.relative_to(self.root_path).as_posix()
        self._nodes.append(
            Node(
                id=node_id,
                type=node_type,
                name=name,
                metadata=NodeMetadata(
                    file_path=relative_file_path,
                    start_line=node.fromlineno,
                    end_line=node.tolineno,
                ),
            )
        )
        return node_id

    def _add_edge(self, source_id: str, target_id: str, edge_type: EdgeType):
        self._edges.append(Edge(source=source_id, target=target_id, type=edge_type))

    def _is_internal_project_symbol(self, inferred: nodes.NodeNG) -> bool:
        """Checks if an inferred node is part of the user's project and not a built-in."""
        if inferred is astroid.Uninferable:
            return False

        # Add a direct check for built-ins before checking the root.
        try:
            if inferred.qname().startswith('builtins.'):
                return False
        except AttributeError:
            # Not all nodes have a qname, which is fine.
            pass

        root = inferred.root()
        if not hasattr(root, 'name'):
            return False

        # Filter out built-in types and functions
        if root.name == 'builtins':
            return False

        # Ensure it has a file path and the path is within our project root
        if hasattr(root, 'file') and root.file:
            inferred_file = Path(root.file)
            if str(inferred_file).startswith(str(self.root_path)):
                return True
        
        return False

    def _visit_module(self, node: nodes.Module):
        module_id = self._add_node(node, NodeType.FILE, node.name)
        self._scope_stack.append(module_id)
        self._default_visit(node)
        self._scope_stack.pop()

    def _visit_classdef(self, node: nodes.ClassDef):
        class_id = self._add_node(node, NodeType.CLASS, node.name)
        self._add_edge(self._scope_stack[-1], class_id, EdgeType.CONTAINS)

        for base in node.bases:
            try:
                for inferred in base.infer():
                    if self._is_internal_project_symbol(inferred):
                        inferred_file = Path(inferred.root().file)
                        target_id = _get_node_id(inferred, inferred_file, self.root_path)
                        self._add_edge(class_id, target_id, EdgeType.INHERITS)
            except astroid.InferenceError:
                continue

        self._scope_stack.append(class_id)
        self._default_visit(node)
        self._scope_stack.pop()

    def _visit_functiondef(self, node: nodes.FunctionDef):
        func_id = self._add_node(node, NodeType.FUNCTION, node.name)
        self._add_edge(self._scope_stack[-1], func_id, EdgeType.CONTAINS)

        if node.decorators:
            for decorator in node.decorators.nodes:
                try:
                    for inferred in decorator.infer():
                        if self._is_internal_project_symbol(inferred):
                            inferred_file = Path(inferred.root().file)
                            target_id = _get_node_id(inferred, inferred_file, self.root_path)
                            self._add_edge(func_id, target_id, EdgeType.DECORATES)
                except astroid.InferenceError:
                    continue

        # Handle type hints in arguments and return type
        all_annotations = node.args.annotations + node.args.kwonlyargs_annotations
        for annotation_node in all_annotations:
            if annotation_node:
                self._handle_annotation(func_id, annotation_node)

        if node.returns:
            self._handle_annotation(func_id, node.returns)

        self._scope_stack.append(func_id)
        self._default_visit(node)
        self._scope_stack.pop()

    def _visit_call(self, node: nodes.Call):
        caller_id = self._scope_stack[-1]
        try:
            for inferred in node.func.infer():
                if inferred is astroid.Uninferable:
                    continue

                # Flag dynamic calls
                try:
                    if inferred.qname() in DYNAMIC_FUNCTION_NAMES:
                        self.dynamic_scope_ids.add(caller_id)
                except AttributeError:
                    # Not a function/method with qname, so can't be one of our dynamic targets.
                    pass

                # Create CALLS edge for internal calls
                if self._is_internal_project_symbol(inferred):
                    inferred_file = Path(inferred.root().file)
                    target_id = _get_node_id(inferred, inferred_file, self.root_path)
                    if caller_id != target_id:
                        self._add_edge(caller_id, target_id, EdgeType.CALLS)
        except astroid.InferenceError:
            pass  # Ignore calls we can't resolve
        self._default_visit(node)

    def _visit_import(self, node: nodes.Import):
        current_file_id = _get_node_id(node.root(), self.file_path, self.root_path)
        for name, _ in node.names:
            try:
                module = node.root().import_module(name)
                if module.file:
                    target_file = Path(module.file)
                    if str(target_file).startswith(str(self.root_path)):
                        relative_target = target_file.relative_to(self.root_path).as_posix()
                        self._add_edge(current_file_id, str(relative_target), EdgeType.IMPORTS)
            except (astroid.AstroidError, ImportError):
                continue

    def _visit_importfrom(self, node: nodes.ImportFrom):
        current_file_id = _get_node_id(node.root(), self.file_path, self.root_path)
        try:
            # Pass the level for correct relative import resolution
            module = node.root().import_module(node.modname, level=node.level)
            if module.file:
                target_file = Path(module.file)
                if str(target_file).startswith(str(self.root_path)):
                    relative_target = target_file.relative_to(self.root_path).as_posix()
                    self._add_edge(current_file_id, str(relative_target), EdgeType.IMPORTS)
        except (astroid.AstroidError, ImportError):
            pass

    def _handle_assign(self, node: nodes.Assign | nodes.AnnAssign):
        # Handles module-level and class-level assignments
        scope_id = self._scope_stack[-1]
        if isinstance(node, nodes.Assign):
            targets = node.targets
        else:  # AnnAssign
            targets = [node.target]

        for target in targets:
            if hasattr(target, 'name'):
                var_id = self._add_node(target, NodeType.VARIABLE, target.name)
                self._add_edge(scope_id, var_id, EdgeType.CONTAINS)

    def _visit_assign(self, node: nodes.Assign):
        self._handle_assign(node)
        self._default_visit(node)

    def _visit_annassign(self, node: nodes.AnnAssign):
        self._handle_assign(node)
        # Handle the type hint from the annotated assignment
        self._handle_annotation(self._scope_stack[-1], node.annotation)
        self._default_visit(node)

    def _handle_annotation(self, source_id: str, annotation_node: nodes.NodeNG):
        """Recursively traverses type hints to find all nested type dependencies."""
        # Base case: A simple name or attribute access (e.g., 'User' or 'models.User')
        if isinstance(annotation_node, (nodes.Name, nodes.Attribute)):
            try:
                for inferred in annotation_node.infer():
                    if self._is_internal_project_symbol(inferred):
                        inferred_file = Path(inferred.root().file)
                        target_id = _get_node_id(inferred, inferred_file, self.root_path)
                        self._add_edge(source_id, target_id, EdgeType.USES_TYPE)
            except astroid.InferenceError:
                pass
        # Recursive case 1: Generic types (e.g., List[User])
        elif isinstance(annotation_node, nodes.Subscript):
            # Recurse on the container (e.g., 'List')
            self._handle_annotation(source_id, annotation_node.value)
            # Recurse on the contents (e.g., 'User')
            self._handle_annotation(source_id, annotation_node.slice)
        # Recursive case 2: Multiple types inside a generic (e.g., the (str, int) in Dict[str, int])
        elif isinstance(annotation_node, nodes.Tuple):
            for element_node in annotation_node.elts:
                self._handle_annotation(source_id, element_node)
        # Recursive case 3: Union types using the '|' operator (e.g., User | None)
        elif isinstance(annotation_node, nodes.BinOp) and annotation_node.op == '|':
            self._handle_annotation(source_id, annotation_node.left)
            self._handle_annotation(source_id, annotation_node.right)

    def _visit_attribute(self, node: nodes.Attribute):
        """Creates USES_VARIABLE edges for attribute access."""
        try:
            for inferred in node.infer():
                if inferred is not astroid.Uninferable:
                    # We are interested in attributes that are variables (AssignName for module/class level, AssignAttr for instance level)
                    if isinstance(inferred, (nodes.AssignName, nodes.AssignAttr)):
                        # Check if it's an internal project symbol
                        if self._is_internal_project_symbol(inferred):
                            inferred_file = Path(inferred.root().file)
                            target_id = _get_node_id(inferred, inferred_file, self.root_path)
                            source_id = self._scope_stack[-1]
                            if source_id != target_id:
                                self._add_edge(source_id, target_id, EdgeType.USES_VARIABLE)
        except astroid.InferenceError:
            pass
        self._default_visit(node)

    def _visit_name(self, node: nodes.Name):
        """Creates USES_VARIABLE edges when a variable is read."""
        # We only care about variables being loaded (read), not stored or deleted.
        if isinstance(node.lookup(node.name)[1][0], (nodes.AssignName, nodes.AssignAttr)):
            try:
                for inferred in node.infer():
                    if inferred is not astroid.Uninferable:
                        # Ensure we are linking to a variable, not a function or class
                        if isinstance(inferred, (nodes.AssignName, nodes.AssignAttr, nodes.Const)):
                            if self._is_internal_project_symbol(inferred):
                                inferred_file = Path(inferred.root().file)
                                target_id = _get_node_id(inferred, inferred_file, self.root_path)
                                source_id = self._scope_stack[-1]
                                if source_id != target_id:
                                    self._add_edge(source_id, target_id, EdgeType.USES_VARIABLE)
            except astroid.InferenceError:
                pass
        self._default_visit(node)


class PythonParser(AbstractParser):
    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.manager = AstroidManager()

    def parse(self, file_path: Path, root_path: Path) -> Tuple[List[Node], List[Edge]]:
        try:
            module = self.manager.ast_from_file(str(file_path))
            visitor = AstroidVisitor(file_path, self.root_path)
            nodes, edges, dynamic_scope_ids = visitor.visit(module)

            # Apply dynamic code flags to the metadata of the relevant nodes
            for node in nodes:
                if node.id in dynamic_scope_ids:
                    node.metadata.contains_dynamic_code = True

            return nodes, edges
        except Exception as e:
            logging.error(f"Failed to parse Python file {file_path}: {e}")
            return [], []
