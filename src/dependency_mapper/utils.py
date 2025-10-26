import shutil


def check_command_installed(command: str) -> None:
    """
    Checks if a command is available in the system's PATH.
    Raises a RuntimeError if the command is not found.
    """
    if shutil.which(command) is None:
        raise RuntimeError(
            f"Command '{command}' not found in PATH. "
            f"Please ensure it is installed and accessible to run the parser."
        )
