"""Logging configuration for the utility"""
import logging
import sys
from pathlib import Path
from config import LOGS_DIR, PROCESSING_LOG, DUPLICATES_LOG, ERRORS_LOG, LOG_FORMAT, LOG_DATE_FORMAT


def setup_logging():
    """Setup all loggers"""

    # Create logs directory if it doesn't exist
    LOGS_DIR.mkdir(exist_ok=True)

    # Create root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Formatter for files
    file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)

    # Formatter for console (without date, with colors)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')

    # 1. Processing logger (all events)
    processing_handler = logging.FileHandler(PROCESSING_LOG, encoding='utf-8')
    processing_handler.setLevel(logging.INFO)
    processing_handler.setFormatter(file_formatter)
    root_logger.addHandler(processing_handler)

    # 2. Error logger
    errors_handler = logging.FileHandler(ERRORS_LOG, encoding='utf-8')
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(file_formatter)
    root_logger.addHandler(errors_handler)

    # 3. Console output with UTF-8
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # 4. Separate logger for duplicates
    duplicates_logger = logging.getLogger('duplicates')
    duplicates_logger.setLevel(logging.INFO)
    duplicates_logger.propagate = False

    duplicates_handler = logging.FileHandler(DUPLICATES_LOG, encoding='utf-8')
    duplicates_handler.setFormatter(file_formatter)
    duplicates_logger.addHandler(duplicates_handler)

    return root_logger, duplicates_logger


def get_logger(name):
    """Get logger by name"""
    return logging.getLogger(name)


# Create main loggers on import
main_logger, duplicates_logger = setup_logging()