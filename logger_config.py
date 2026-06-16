import logging
import sys
from pathlib import Path
from config import LOGS_DIR, PROCESSING_LOG, DUPLICATES_LOG, ERRORS_LOG, LOG_FORMAT, LOG_DATE_FORMAT


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    file_formatter = logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT)
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')

    processing_handler = logging.FileHandler(PROCESSING_LOG, encoding='utf-8')
    processing_handler.setLevel(logging.INFO)
    processing_handler.setFormatter(file_formatter)
    root_logger.addHandler(processing_handler)

    errors_handler = logging.FileHandler(ERRORS_LOG, encoding='utf-8')
    errors_handler.setLevel(logging.ERROR)
    errors_handler.setFormatter(file_formatter)
    root_logger.addHandler(errors_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    duplicates_logger = logging.getLogger('duplicates')
    duplicates_logger.setLevel(logging.INFO)
    duplicates_logger.propagate = False

    duplicates_handler = logging.FileHandler(DUPLICATES_LOG, encoding='utf-8')
    duplicates_handler.setFormatter(file_formatter)
    duplicates_logger.addHandler(duplicates_handler)

    return root_logger, duplicates_logger

def get_logger(name):
    return logging.getLogger(name)

main_logger, duplicates_logger = setup_logging()