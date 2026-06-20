import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config import BASE_DIR

LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "dictadesk.log"
_CONFIGURED = False


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("dictadesk")
    if _CONFIGURED:
        return logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(formatter)
    logger.addHandler(console)

    _CONFIGURED = True
    return logger


def get_logger(name: str = "dictadesk") -> logging.Logger:
    setup_logging()
    return logging.getLogger(name)
