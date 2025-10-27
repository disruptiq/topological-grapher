import argparse
import os
import sys
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
        help="Path to save the output file in the specified format. If not provided, saves both JSON and DOT formats to 'output/' directory.",
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
    try:
        # Pass the number of workers from the CLI to the API.
        graph = generate_graph(root_path, num_workers=args.workers)
    except KeyboardInterrupt:
        print("\nInterrupted by user. Terminating...")
        sys.exit(1)
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

    if args.output_file:
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

        try:
            args.output_file.write_text(output_str, encoding="utf-8")
            print(f"Successfully saved graph to {args.output_file}")
        except IOError as e:
            parser.error(f"Error writing to output file '{args.output_file}': {e}")
    else:
        # Create output directory and save both formats
        os.makedirs("output", exist_ok=True)

        # Save JSON format
        serializer = JsonSerializer()
        output_str = serializer.serialize(graph)
        json_path = Path("output/dependency_graph.json")
        try:
            json_path.write_text(output_str, encoding="utf-8")
            print(f"Successfully saved JSON graph to {json_path}")
        except IOError as e:
            parser.error(f"Error writing JSON to output file '{json_path}': {e}")

        # Save DOT format
        try:
            serializer = DotSerializer()
            output_str = serializer.serialize(graph)
            dot_path = Path("output/dependency_graph.dot")
            dot_path.write_text(output_str, encoding="utf-8")
            print(f"Successfully saved DOT graph to {dot_path}")
        except ImportError as e:
            print(f"Warning: Could not generate DOT format: {e}")
        except IOError as e:
            parser.error(f"Error writing DOT to output file '{dot_path}': {e}")



        print("All outputs saved to 'output/' directory")

    duration = end_time - start_time
    print(f"Found {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges.")
    print(f"Analysis completed in {duration:.2f} seconds.")


if __name__ == "__main__":
    main()
