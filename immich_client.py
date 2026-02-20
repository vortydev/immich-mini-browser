# File: immich_client.py
from __future__ import annotations
import requests
from typing import List, Optional, Any
import pandas as pd

from config import IMMICH_BASE_URL, IMMICH_API_KEY, IMAGES_DIR, CSV_DIR
from immich_models import ImmichAsset, ImmichAlbum




class ImmichClient:
    def __init__(self, base_url: Optional[str] = None, api_key: Optional[str] = None):
        self.base = (base_url or IMMICH_BASE_URL).rstrip("/")
        self.key = api_key or IMMICH_API_KEY
        if not self.base or not self.key:
            raise ValueError("IMMICH_BASE_URL and IMMICH_API_KEY must be set.")
        self.headers = {"x-api-key": self.key}

    # ----------------------------- Helpers ---------------------------------
    # Tags
    def list_tags(self):
        r = requests.get(f"{self.base}/api/tags", headers=self.headers, timeout=30)
        r.raise_for_status(); return r.json()

    def tag_assets(self, tag_id: str, asset_ids: list[str]):
        r = requests.put(f"{self.base}/api/tags/{tag_id}/assets",
                         headers=self.headers, json={"ids": asset_ids}, timeout=30)
        r.raise_for_status(); return r.json()

    # People
    def list_people(self, page=1, size=100):
        r = requests.get(f"{self.base}/api/people", headers=self.headers,
                         params={"page": page, "size": size}, timeout=30)
        r.raise_for_status(); return r.json()

    def get_person_assets(self, person_id: str, page=1, size=100):
        r = requests.get(f"{self.base}/api/people/{person_id}/assets",
                         headers=self.headers, params={"page": page, "size": size}, timeout=60)
        r.raise_for_status(); return r.json()

    # Shared links (albums)
    def list_shared_links(self, album_id: str | None = None):
        params = {"albumId": album_id} if album_id else None
        r = requests.get(f"{self.base}/api/shared-links", headers=self.headers, params=params, timeout=30)
        r.raise_for_status(); return r.json()

    # ----------------------------- Assets ----------------------------------
    def get_asset(self, asset_id: str) -> dict:
        url = f"{self.base}/api/assets/{asset_id}"
        r = requests.get(url, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def get_thumbnail(self, asset_id: str, size: str = "preview", save: bool = False) -> bytes:
        url = f"{self.base}/api/assets/{asset_id}/thumbnail"
        r = requests.get(url, headers=self.headers, params={"size": size}, timeout=30)
        r.raise_for_status()
        data = r.content
        if save:
            out_path = IMAGES_DIR / f"{asset_id}_thumb.jpg"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)
            print(f"Thumbnail saved to {out_path}")
        return data

    def stream_original(self, asset_id: str):
        # Immich original file stream (works across current versions)
        url = f"{self.base}/api/assets/{asset_id}/original"
        # requests follows 302/307 by default even with stream=True
        r = requests.get(url, headers=self.headers, stream=True, timeout=120)
        r.raise_for_status()
        return r

    # ----------------------------- Albums ----------------------------------
    def list_albums(self, as_df: bool = False):
        url = f"{self.base}/api/albums"
        r = requests.get(url, headers=self.headers, timeout=30)
        r.raise_for_status()
        albums = r.json()
        if as_df:
            if pd is None:
                raise RuntimeError("pandas is not installed. Run: pip install pandas")
            rows = [
                {
                "id": a.get("id"),
                "albumName": a.get("albumName"),
                "createdAt": a.get("createdAt"),
                "assetCount": a.get("assetCount"),
                }
                for a in albums
            ]
            return pd.DataFrame(rows)
        return albums

    def get_album(self, album_id: str) -> dict:
        url = f"{self.base}/api/albums/{album_id}"
        r = requests.get(url, headers=self.headers, timeout=30)
        r.raise_for_status()
        return r.json()

    def list_album_assets(self, album_id: str) -> list[dict]:
        """Return a list of asset objects for an album.
        Immich versions vary; we first fetch the album and try to read assets.
        """
        album = self.get_album(album_id)
        assets = album.get("assets")
        if isinstance(assets, list):
            return assets
        # Fallback: some versions return only IDs; try a second call if needed
        return []
    
    def list_album_assets_page(self, album_id: str, page: int = 1, per_page: int = 48) -> dict:
        """
        Robust pagination:
        - Try server-side (take/skip) ONLY for page 1 and only accept it if
        len(assets) <= per_page. Otherwise, fetch-all and slice locally.
        - For page > 1, ALWAYS fetch-all and slice locally (some Immich builds
        ignore 'skip' and return page 1 again).
        """
        page = max(1, int(page))
        per_page = max(1, min(int(per_page), 200))

        # Try to read declared total (best-effort)
        try:
            meta = self.get_album(album_id)
            total_meta = int(meta.get("assetCount") or 0)
        except Exception:
            total_meta = 0

        # Attempt server-side pagination (Immich versions may support take/skip)
        try:
            url = f"{self.base}/api/albums/{album_id}"
            params = {"take": per_page, "skip": (page - 1) * per_page}
            r = requests.get(url, headers=self.headers, params=params, timeout=30)
            if r.ok:
                data = r.json()
                assets = data.get("assets") or []
                total = int(data.get("assetCount") or len(assets))
                # If Immich returned some assets, trust it
                if isinstance(assets, list) and (assets or total):
                    return {"items": assets, "total": total, "page": page, "per_page": per_page}
            else:
                # keep the error but fall back
                err = f"{r.status_code} {r.text[:200]}"
        except Exception as e:
            err = str(e)

        # Page 1: one attempt at server-side pagination
        if page == 1:
            try:
                url = f"{self.base}/api/albums/{album_id}"
                params = {"take": per_page, "skip": 0}
                r = requests.get(url, headers=self.headers, params=params, timeout=30)
                if r.ok:
                    data = r.json()
                    assets = data.get("assets") or []
                    # Only trust if Immich returns at most per_page items
                    if isinstance(assets, list) and len(assets) <= per_page:
                        total = int(data.get("assetCount") or total_meta or len(assets))
                        return {"items": assets, "total": total, "page": page, "per_page": per_page}
            except Exception:
                pass  # fall through to client-side

        # Client-side fallback for all other cases (incl. page>1)
        try:
            all_assets = self.list_album_assets(album_id) or []
            total = len(all_assets)
            start = (page - 1) * per_page
            end = start + per_page
            items = all_assets[start:end] if start < len(all_assets) else []
            return {"items": items, "total": total, "page": page, "per_page": per_page}
        except Exception as e:
            # Return an empty page with the error message so callers can handle gracefully
            return {"items": [], "total": 0, "page": page, "per_page": per_page, "error": str(e)}

    # ------------------------ DataFrame helpers ----------------------------
    def list_album_assets_df(self, album_id: str, columns: Optional[list[str]] = None):
        if pd is None:
            raise RuntimeError("pandas is not installed. Run: pip install pandas")

        raw = self.list_album_assets(album_id)
        rows: list[dict[str, Any]] = [self._flatten_asset(a) for a in raw]
        df = pd.DataFrame(rows)
        if columns:
            existing = [c for c in columns if c in df.columns]
            df = df[existing]
        return df

    @staticmethod
    def _flatten_asset(a: dict) -> dict:
        exif = a.get("exifInfo") or a.get("exif") or {}
        owner = a.get("owner") or {}
        device = a.get("deviceInfo") or {}
        return {
            "id": a.get("id"),
            "deviceAssetId": a.get("deviceAssetId"),
            "type": a.get("type"),
            "fileCreatedAt": a.get("fileCreatedAt"),
            "fileModifiedAt": a.get("fileModifiedAt"),
            "originalFileName": a.get("originalFileName"),
            "duration": a.get("duration"),
            "ownerId": owner.get("id"),
            "ownerName": owner.get("name") or owner.get("email"),
            "deviceId": device.get("deviceId"),
            "exif.make": exif.get("make"),
            "exif.model": exif.get("model"),
            "exif.fNumber": exif.get("fNumber"),
            "exif.focalLength": exif.get("focalLength"),
            "exif.iso": exif.get("iso"),
            "exif.exposureTime": exif.get("exposureTime"),
            "exif.latitude": exif.get("latitude"),
            "exif.longitude": exif.get("longitude"),
            "exif.orientation": exif.get("orientation"),
        }
    
    # ---------------------- Object helpers ----------------------
    def get_asset_obj(self, asset_id: str) -> ImmichAsset:
        data = self.get_asset(asset_id)
        return ImmichAsset.from_api(self, data)

    def list_albums_obj(self) -> List[ImmichAlbum]:
        albums = self.list_albums(as_df=False)
        return [ImmichAlbum.from_api(self, a) for a in albums]

    def get_album_obj(self, album_id: str) -> ImmichAlbum:
        data = self.get_album(album_id)
        return ImmichAlbum.from_api(self, data)


if __name__ == "__main__":
    import sys
    client = ImmichClient()

    if len(sys.argv) == 1:
        print("""Usage:
    python immich_client.py albums [df]
    python immich_client.py album-df <album_id>
    python immich_client.py <asset_id>""")
        raise SystemExit(1)

    cmd = sys.argv[1]
    if cmd == "albums":
        if len(sys.argv) > 2 and sys.argv[2] == "df":
            df = client.list_albums(as_df=True)
            print(df.to_string(index=False))
            out = CSV_DIR / "immich_albums.csv"
            df.to_csv(out, index=False)
            print(f"Saved CSV -> {out}")
        else:
            for a in client.list_albums():
                print(f"- {a.get('id')} :: {a.get('albumName')}")
    elif cmd == "album-df":
        if len(sys.argv) < 3:
            print("Provide an album_id: python immich_client.py album-df <album_id>")
            raise SystemExit(2)
        album_id = sys.argv[2]
        df = client.list_album_assets_df(album_id)
        try:
            print(df.head(10).to_string(index=False))
            out = CSV_DIR / f"immich_album_{album_id}.csv"
            df.to_csv(out, index=False)
            print(f"Saved CSV -> {out}")
        except Exception as e:
            print("Error displaying/saving DataFrame:", e)
    else:
        asset_id = cmd
        info = client.get_asset(asset_id)
        print("Asset info:", info)
        thumb_bytes = client.get_thumbnail(asset_id, save=True)
