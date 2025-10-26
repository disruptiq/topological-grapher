from typing import List

import networkx as nx

from .models import Edge, Node


class GraphBuilder:
    def __init__(self):
        self.graph = nx.DiGraph()

    def build(self, nodes: List[Node], edges: List[Edge]) -> nx.DiGraph:
        for node in nodes:
            self.graph.add_node(node.id, **node.model_dump(mode='json'))
        for edge in edges:
            self.graph.add_edge(edge.source, edge.target, type=edge.type.value)
        return self.graph
