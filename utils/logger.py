"""
Logging utility for the restaurant automation system.
Provides structured logging with file and console output.
"""

import os
import sys
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler


def get_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """
    Get or create a logger with console and file handlers.

    Args:
        name: Logger name (usually __name__)
        log_dir: Directory for log files

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Ensure log directory exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Formatter
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (rotating, 10MB per file, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_path / "automation.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
