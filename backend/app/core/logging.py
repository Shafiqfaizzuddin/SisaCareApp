"""Application logging setup using the Python standard library."""

from __future__ import annotations

import logging


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(level: str) -> None:
    """Configure application loggers without replacing Uvicorn's handlers."""

    logging.basicConfig(level=logging.WARNING, format=LOG_FORMAT)
    logging.getLogger("app").setLevel(level)


__all__ = ["configure_logging"]
