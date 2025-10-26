import json

import networkx as nx
from networkx.readwrite import json_graph


class JsonSerializer:
    def serialize(self, graph: nx.DiGraph, indent: int = 2) -> str:
        # Explicitly set edges="links" to preserve current behavior and remove the warning.
        data = json_graph.node_link_data(graph, edges="links")
        return json.dumps(data, indent=indent)


class DotSerializer:
    def serialize(self, graph: nx.DiGraph) -> str:
        """Serializes the graph to the DOT language format."""
        try:
            from networkx.drawing.nx_pydot import to_pydot
        except ImportError as e:
            raise ImportError(
                "DOT serialization requires pydot. Please install it using: pip install pydot"
            ) from e
        
        # Create a copy to modify for visualization without affecting the original graph
        viz_graph = graph.copy()

        # Keep only the simple name for cleaner labels
        for node, data in viz_graph.nodes(data=True):
            data['label'] = data.get('name', node).split(':')[-1] # Show simple name
            if 'name' in data:
                del data['name']

        pydot_graph = to_pydot(viz_graph)
        return pydot_graph.to_string()
