"""Attaching the run's log file, so the log and the artifacts live in one folder."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Final

RUN_LOG_FILENAME: Final[str] = "run.log"


@contextmanager
def attached_run_log(logger: logging.Logger, run_directory: Path, formatter: logging.Formatter) -> Generator[logging.FileHandler]:
    """Write everything `logger` emits to `<run directory>/run.log` for the duration of the block.

    The handler is removed and closed on exit, even if the block raises. If the logger would
    drop INFO records, it is lowered to INFO for the block and restored afterwards.
    """
    handler: logging.FileHandler = logging.FileHandler(run_directory / RUN_LOG_FILENAME, encoding="utf-8")
    handler.setFormatter(formatter)
    previous_level: int = logger.level
    logger.addHandler(handler)
    if logger.getEffectiveLevel() > logging.INFO:
        logger.setLevel(logging.INFO)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        handler.close()
        logger.setLevel(previous_level)
