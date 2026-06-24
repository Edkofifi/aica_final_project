"""
Configures a single shared logger for the entire pipeline.
Call get_logger(__name__) at the top of any module to get a
pre-configured logger that writes to both console and log file.
"""

import logging
import os
from utils.config import LOG_DIR, LOG_FILE, LOG_LEVEL, LOG_FORMAT, LOG_DATE


def get_logger(name: str) -> logging.Logger:
    """
    Return a named logger.  The first call also wires up the handlers;
    subsequent calls for the same name reuse the existing logger.

    Args:
        name: Typically __name__ from the calling module.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if get_logger is called more than once.
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, LOG_LEVEL))

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=LOG_DATE)

    # Console handler when running manually or in Airflow task logs.
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler to persists logs for audit and debugging.
    os.makedirs(LOG_DIR, exist_ok=True)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
