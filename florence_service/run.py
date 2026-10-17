"""Start one worker on the configured loopback interface."""

import os
from pathlib import Path

import uvicorn

from .settings import load_settings


if __name__ == "__main__":
    os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parent / ".cache" / "huggingface"))
    config = load_settings()
    uvicorn.run("florence_service.app:app", host=config.host, port=config.port, workers=1)
