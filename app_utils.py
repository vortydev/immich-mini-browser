# app_utils.py
import os
import hashlib
from datetime import datetime
import pytz
from pathlib import Path
from flask import send_file

from config import LOCAL_TZ

def _album_cover_asset_id(album: dict) -> str | None:
    cover = album.get("albumCoverAssetId") or album.get("albumThumbnailAssetId") or album.get("coverAssetId")
    if cover:
        return cover
    assets = album.get("assets")
    if isinstance(assets, list) and assets:
        # assets may be either full objects or {id: ...}; try both
        first = assets[0]
        return first.get("id") if isinstance(first, dict) else None
    return None

def _send_cached_image(path: str | os.PathLike):
    p = Path(path)
    # Strong ETag from file size + mtime
    etag = hashlib.md5(f"{p.stat().st_mtime_ns}-{p.stat().st_size}".encode()).hexdigest()
    resp = send_file(str(p), mimetype="image/jpeg", conditional=True, last_modified=p.stat().st_mtime)
    resp.set_etag(etag)
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp

def _fmt_date(dt_str: str) -> str:
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt_utc = dt.astimezone(pytz.UTC)
        dt_local = dt_utc.astimezone(pytz.timezone(LOCAL_TZ))
        return dt_local.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return dt_str
    
def print_routes(app, label: str = None):
    lines = [str(r) for r in app.url_map.iter_rules()]
    width = max((len(s) for s in lines), default=0)

    bar = "=" * width
    
    if label is not None:
        print(bar)
        print("Routes")

    print(bar)
    for s in sorted(lines):
        print(s)
    print(bar)