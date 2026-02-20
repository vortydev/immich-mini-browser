# immich_cache.py
from __future__ import annotations
import time
import json
from pathlib import Path
from typing import Optional
from pprint import pprint

from config import TTL_THUMBS, TTL_META, THUMB_DIR, META_DIR
from immich_client import ImmichClient


# ========== Helpers ==========

def _fresh(path: Path) -> bool:
    if TTL_THUMBS <= 0:
        return path.exists()
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < TTL_THUMBS

def _dir_bytes_and_count(root: Path) -> tuple[int, int]:
    """Return (files, bytes) for all regular files under root."""
    files = 0
    total_bytes = 0
    if not root.exists():
        return (0, 0)
    for p in root.rglob("*"):
        if p.is_file():
            files += 1
            try:
                total_bytes += p.stat().st_size
            except FileNotFoundError:
                pass
    return files, total_bytes

def _is_fresh_file(path: Path, ttl: int) -> bool:
    if ttl <= 0:
        return path.exists()
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age < ttl

def _read_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(path)


class ImmichCache:
    """
    Simple thumbnail cache.
    - kind='images' caches by asset_id in thumbnails/images/<asset_id>_<size>.jpg
    - kind='albums' caches by album_id in thumbnails/albums/<album_id>_<size>.jpg
      (file content is fetched from the *cover asset id*, but key is album_id)
    """
    def __init__(self, base_dir: Optional[str | Path] = None):
        self.base = Path(base_dir).resolve() if base_dir else THUMB_DIR
        (self.base / "albums").mkdir(parents=True, exist_ok=True)
        (self.base / "images").mkdir(parents=True, exist_ok=True)

    def _path_for(self, *, kind: str, key: str, size: str) -> Path:
        if kind not in ("albums", "images"):
            raise ValueError("kind must be 'albums' or 'images'")
        safe_key = key.replace("/", "_")
        return (self.base / kind / f"{safe_key}_{size}.jpg")

    def fetch_or_cache(self, client: ImmichClient, asset_id: str, *, kind: str, key: Optional[str] = None, size: str = "preview", force: bool = False, ) -> Path:
        cache_key = key or asset_id
        path = self._path_for(kind=kind, key=cache_key, size=size)

        if not force and _fresh(path):
            print(f"[thumb cache] HIT  {kind}:{cache_key} size={size} -> {path}")
            return path

        # Pull fresh bytes from Immich and write
        print(f"[thumb cache] MISS {kind}:{cache_key} size={size} -> fetching from Immich")
        data = client.get_thumbnail(asset_id, size=size, save=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path
    
    # ---------- METADATA CACHE (albums + assets) ----------

    def _albums_meta_path(self) -> Path:
        return META_DIR / "albums.json"

    def _album_assets_meta_path(self, album_id: str) -> Path:
        safe = album_id.replace("/", "_")
        return META_DIR / f"album_{safe}_assets.json"

    # Albums list -----------------------------------------------------------
    def get_or_fetch_albums(self, client: ImmichClient, *, ttl: int = TTL_META, force: bool = False) -> list[dict]:
        """
        Returns cached album list if fresh; otherwise fetches from Immich,
        stores to cache, and returns it.
        """
        p = self._albums_meta_path()
        if not force and _is_fresh_file(p, ttl):
            data = _read_json(p)
            if isinstance(data, list):
                # print("[meta cache] HIT albums")
                return data

        # Fetch fresh
        # print("[meta cache] MISS albums -> fetch")
        albums = client.list_albums()
        _write_json(p, albums or [])
        return albums or []

    def clear_albums_meta(self) -> int:
        """Remove albums list cache file. Returns 1 if deleted, 0 otherwise."""
        p = self._albums_meta_path()
        if p.exists():
            p.unlink(missing_ok=True)
            return 1
        return 0

    # Per-album assets ------------------------------------------------------
    def get_or_fetch_album_assets(self, client: ImmichClient, album_id: str, *, ttl: int = TTL_META, force: bool = False) -> list[dict]:
        """
        Returns cached assets list for an album if fresh; otherwise fetches from Immich,
        stores to cache, and returns it.
        """
        p = self._album_assets_meta_path(album_id)
        if not force and _is_fresh_file(p, ttl):
            data = _read_json(p)
            if isinstance(data, list):
                # print(f"[meta cache] HIT album-assets {album_id}")
                return data

        # Fetch fresh
        # print(f"[meta cache] MISS album-assets {album_id} -> fetch")
        assets = client.list_album_assets(album_id) or []
        _write_json(p, assets)
        return assets

    def clear_album_assets_meta(self, album_id: str) -> int:
        """Remove cached assets for one album. Returns 1 if deleted, 0 otherwise."""
        p = self._album_assets_meta_path(album_id)
        if p.exists():
            p.unlink(missing_ok=True)
            return 1
        return 0

    # Bulk clear ------------------------------------------------------------
    def clear_all_meta(self) -> int:
        """Delete all metadata cache files (albums + per-album). Returns count removed."""
        count = 0
        if META_DIR.exists():
            for path in META_DIR.glob("*.json"):
                try:
                    path.unlink(missing_ok=True)
                    count += 1
                except Exception:
                    pass
        return count
    
    def count_cached(self, kind: str | None = None) -> dict:
        """
        Get cached file counts and sizes.
        kind: None -> both, or 'albums' / 'images'
        Returns: {"albums": {"files": int, "bytes": int},
                  "images": {"files": int, "bytes": int},
                  "total_files": int, "total_bytes": int}
        """
        kinds = ("albums", "images") if kind is None else (kind,)
        out = {"albums": {"files": 0, "bytes": 0},
               "images": {"files": 0, "bytes": 0}}

        for k in kinds:
            root = self.base / k
            files, bytes_ = _dir_bytes_and_count(root)
            out[k]["files"] = files
            out[k]["bytes"] = bytes_

        out["total_files"] = out["albums"]["files"] + out["images"]["files"]
        out["total_bytes"] = out["albums"]["bytes"] + out["images"]["bytes"]
        return out

    def clear_cache(self, kind: str | None = None) -> int:
        """
        Delete cached files.
        kind: None -> clear both 'albums' and 'images'; or pass one of them.
        Returns number of files removed.
        """
        kinds = ("albums", "images") if kind is None else (kind,)
        removed = 0

        for k in kinds:
            root = self.base / k
            if not root.exists():
                continue
            # remove all files under the subtree
            for p in root.rglob("*"):
                if p.is_file():
                    try:
                        p.unlink()
                        removed += 1
                    except FileNotFoundError:
                        pass
            # optional: prune empty dirs
            for d in sorted(root.rglob("*"), key=lambda x: len(x.parts), reverse=True):
                if d.is_dir():
                    try:
                        next(d.iterdir())
                    except StopIteration:
                        d.rmdir()
        return removed
        
    

if __name__ == "__main__":
    c = ImmichCache()
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "stats":
        pprint(c.count_cached())
    elif cmd == "clear":
        kind = sys.argv[2] if len(sys.argv) > 2 else None
        print(f"Removed {c.clear_cache(kind)} files")
    else:
        print("Usage: python immich_cache.py [stats|clear [albums|images]]")
