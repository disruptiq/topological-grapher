import argparse
import time
from pathlib import Path

from .api import CircularDependencyError, generate_graph, get_analysis_layers
from .serializers import DotSerializer, JsonSerializer


def main():
    """
    Main function to run the command-line interface.
    """
    parser = argparse.ArgumentParser(
        description="Generates a dependency graph for the codebase at the specified path."
    )
    parser.add_argument(
        "root_path",
        type=Path,
        help="The root directory of the codebase to analyze.",
    )
    parser.add_argument(
        "--output",
        "-o",
        dest="output_file",
        type=Path,
        default=None,
        help="Path to save the output JSON file. If not provided, prints to standard output.",
    )
    parser.add_argument(
        "--workers",
        "-w",
        type=int,
        default=None,
        help="Number of parallel worker processes to use. Defaults to the number of CPU cores.",
    )
    parser.add_argument(
        "--format",
        "-f",
        type=str,
        default="json",
        choices=["json", "dot"],
        help="The output format for the graph (default: json).",
    )
    parser.add_argument(
        "--show-layers",
        action="store_true",
        help="Perform a topological sort and print analysis layers. Incompatible with --output.",
    )

    args = parser.parse_args()

    if args.show_layers and args.output_file:
        parser.error("--show-layers cannot be used with --output.")

    # Manual validation to ensure robustness
    root_path: Path = args.root_path.resolve()
    if not root_path.exists():
        parser.error(f"Error: The path '{args.root_path}' does not exist.")
    if not root_path.is_dir():
        parser.error(f"Error: The path '{args.root_path}' is not a directory.")

    print(f"Analyzing codebase at: {root_path}")

    start_time = time.perf_counter()
    # Pass the number of workers from the CLI to the API.
    graph = generate_graph(root_path, num_workers=args.workers)
    end_time = time.perf_counter()

    if args.show_layers:
        try:
            layers = get_analysis_layers(graph)
            print("Analysis Layers:")
            for i, layer in enumerate(layers):
                print(f"  Layer {i}: {len(layer)} nodes")
        except CircularDependencyError as e:
            parser.error(f"Error: {e}")
        
        return # Skip normal output

    output_str = ""
    if args.format == "json":
        serializer = JsonSerializer()
        output_str = serializer.serialize(graph)
    elif args.format == "dot":
        serializer = DotSerializer()
        try:
            output_str = serializer.serialize(graph)
        except ImportError as e:
            parser.error(f"Error: {e}")

    if args.output_file:
        try:
            args.output_file.write_text(output_str, encoding="utf-8")
            print(f"Successfully saved graph to {args.output_file}")
        except IOError as e:
            parser.error(f"Error writing to output file '{args.output_file}': {e}")
    else:
        print(output_str)

    duration = end_time - start_time
    print(f"Found {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges.")
    print(f"Analysis completed in {duration:.2f} seconds.")


if __name__ == "__main__":
    main()
