import logging
import logging.handlers
import os
import queue


def setup_logger(name, log_file):
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Vermeide doppelte Handler
    if not logger.handlers:
        handler = logging.handlers.QueueHandler(queue.Queue(-1))
        logger.addHandler(handler)

        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger