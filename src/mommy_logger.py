"""
Mommy-pulsy logger with personality.
"""

import sys
from typing import Optional


class MommyLogger:
    """Logger with mommy personality."""

    def __init__(self, name: str = "mommy-pulsy"):
        self.name = name
        self._prefix = f"[{name}]"

    def _print(self, message: str, file=sys.stdout):
        """Print a message with the prefix."""
        print(f"{self._prefix} {message}", file=file)

    def info(self, message: str):
        """Print an informational message."""
        self._print(message)

    def warn(self, message: str):
        """Print a warning message."""
        self._print(message, file=sys.stderr)

    def error(self, message: str):
        """Print an error message."""
        self._print(message, file=sys.stderr)

    def greet(self):
        """Print a greeting message."""
        self._print("Hi, sweetheart. ♡")

    def goodbye(self):
        """Print a goodbye message."""
        self._print("Goodbye, darling. ♡")

    def success(self, message: str):
        """Print a success message."""
        self._print(f"{message} ♪")

    def concern(self, message: str):
        """Print a concerned message."""
        self._print(f"Hmm... {message}")

    def reassurance(self, message: str):
        """Print a reassuring message."""
        self._print(f"{message} ♡")

    def tease(self, message: str):
        """Print a teasing message."""
        self._print(f"{message} 😏")

    def pride(self, message: str):
        """Print a proud message."""
        self._print(f"{message} ✨")

    def aww(self, message: str):
        """Print an aww message."""
        self._print(f"Awww, {message} 🥺")

    def technical_error(self, context: str, details: Optional[str] = None):
        """Print a technical error with context."""
        self.concern(context)
        if details:
            self._print(details, file=sys.stderr)


_logger_instance: Optional[MommyLogger] = None


def get_logger() -> MommyLogger:
    """Get the singleton logger instance."""
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = MommyLogger()
    return _logger_instance
