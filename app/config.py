"""Deployment configuration; secrets stay in environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(os.getenv("DATA_ROOT", str(ROOT / "data")))
    model_url: str = os.getenv("MODEL_BASE_URL", "")
    model_name: str = os.getenv("MODEL_NAME", "")
    model_key: str = os.getenv("MODEL_API_KEY", "")
    max_upload: int = int(os.getenv("MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
    model_timeout: int = int(os.getenv("MODEL_TIMEOUT", "600"))
