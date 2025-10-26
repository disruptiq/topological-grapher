import fnmatch
import subprocess
from pathlib import Path
from typing import Generator, List

DEFAULT_IGNORE_PATTERNS = [".*", "__pycache__", "build", "dist", "*.egg-info", "venv", ".venv", "node_modules"]
SUPPORTED_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx"}


class GitFileWalker:
    def __init__(self, root_path: Path):
        self.root_path = root_path

    def walk(self) -> Generator[Path, None, None]:
        try:
            cmd = ["git", "ls-files", "--cached", "--others", "--exclude-standard"]
            result = subprocess.run(
                cmd,
                cwd=self.root_path,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf-8",
            )
            for line in result.stdout.strip().split("\n"):
                if line and Path(line).suffix in SUPPORTED_EXTENSIONS:
                    yield self.root_path / line
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to FileSystemWalker if git is not available or it's not a repo
            yield from FileSystemWalker(self.root_path).walk()


class FileSystemWalker:
    def __init__(self, root_path: Path, ignore_patterns: List[str] = None):
        self.root_path = root_path
        self.ignore_patterns = ignore_patterns or DEFAULT_IGNORE_PATTERNS

    def walk(self) -> Generator[Path, None, None]:
        for extension in SUPPORTED_EXTENSIONS:
            for file_path in self.root_path.rglob(f"*{extension}"):
                if self._is_ignored(file_path):
                    continue
                yield file_path

    def _is_ignored(self, path: Path) -> bool:
        relative_path = path.relative_to(self.root_path)
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(relative_path, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
            for part in relative_path.parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
        return False


def get_file_walker(root_path: Path) -> GitFileWalker | FileSystemWalker:
    if (root_path / ".git").is_dir():
        return GitFileWalker(root_path)
    return FileSystemWalker(root_path)
