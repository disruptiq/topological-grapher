#!/usr/bin/env python3
"""
Entry point for the topological-grapher application.
"""

import sys
from pathlib import Path

# Add the src directory to the Python path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from dependency_mapper.cli import main

if __name__ == "__main__":
    main()
