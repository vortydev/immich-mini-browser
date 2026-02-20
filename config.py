# config.py
import os
import dotenv
from pathlib import Path

# ========== Load environment ==========
dotenv.load_dotenv()

LOCAL_TZ = os.getenv("LOCAL_TZ", "America/Toronto")
ENV_MODE = os.getenv("ENV_MODE", "prod")
VERSION = os.getenv("VERSION")

# Flask
FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
PER_PAGE = int(os.getenv("DEFAULT_PER_PAGE", "20"))

# Immich
IMMICH_BASE_URL = os.getenv("IMMICH_BASE_URL", "").rstrip("/")
IMMICH_API_KEY = os.getenv("IMMICH_API_KEY", "")

# TTL (seconds). 0 or missing = never expire.
TTL_THUMBS = int(os.getenv("IMMICH_THUMB_TTL_SECONDS", "0") or "0")
TTL_META = int(os.getenv("IMMICH_META_TTL_SECONDS", "300") or "300")  # 5 min default

# Paths for saving outputs
BASE_DIR = Path(os.getenv("IMMICH_DATA_DIR", "data")).resolve()
THUMB_DIR = BASE_DIR / "thumbnails"
CSV_DIR  = BASE_DIR / "csv_exports"
META_DIR = BASE_DIR / "meta"
ALBUMS_DIR = THUMB_DIR / "albums"
IMAGES_DIR = THUMB_DIR / "images"

# Ensure dirs exist
for d in (THUMB_DIR, CSV_DIR, META_DIR, ALBUMS_DIR, IMAGES_DIR):
    Path(d).mkdir(parents=True, exist_ok=True)