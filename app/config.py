from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL = os.getenv("MODEL", "google/gemma-4-31b-it:free").strip()

TEACHER_INVITE_CODE = os.getenv("TEACHER_INVITE_CODE", "").strip()
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))

UPLOAD_DIR = Path(os.getenv("NUDGE_UPLOAD_DIR", str(BASE_DIR / "uploads")))
DATA_DIR = Path(os.getenv("NUDGE_DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = Path(os.getenv("NUDGE_DB_PATH", str(DATA_DIR / "nudge.db")))

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
