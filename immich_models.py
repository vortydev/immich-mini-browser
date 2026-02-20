# immich_models.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple, Union, TYPE_CHECKING
import requests

try:
    import pandas as pd  # optional; used for DataFrame helpers
except Exception:  # pragma: no cover
    pd = None

if TYPE_CHECKING:
    from .immich_client import ImmichClient


# ----------------------------- Models --------------------------------------


@dataclass(frozen=True)
class ImmichAsset:
    """
    A lightweight, immutable representation of an Immich asset with
    convenience helpers to fetch thumbnails/originals and flatten EXIF.
    """
    client: "ImmichClient"
    id: str
    device_asset_id: Optional[str] = None
    type: Optional[str] = None
    file_created_at: Optional[str] = None
    file_modified_at: Optional[str] = None
    original_file_name: Optional[str] = None
    duration: Optional[Union[int, float, str]] = None
    owner_id: Optional[str] = None
    owner_name: Optional[str] = None
    device_id: Optional[str] = None
    exif: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    # ---------- Construction ----------
    @staticmethod
    def from_api(client: "ImmichClient", payload: Dict[str, Any]) -> "ImmichAsset":
        exif = payload.get("exifInfo") or payload.get("exif") or {}
        owner = payload.get("owner") or {}
        device = payload.get("deviceInfo") or {}

        return ImmichAsset(
            client=client,
            id=payload.get("id"),
            device_asset_id=payload.get("deviceAssetId"),
            type=payload.get("type"),
            file_created_at=payload.get("fileCreatedAt"),
            file_modified_at=payload.get("fileModifiedAt"),
            original_file_name=payload.get("originalFileName"),
            duration=payload.get("duration"),
            owner_id=owner.get("id"),
            owner_name=owner.get("name") or owner.get("email"),
            device_id=device.get("deviceId"),
            exif={
                "make": exif.get("make"),
                "model": exif.get("model"),
                "fNumber": exif.get("fNumber"),
                "focalLength": exif.get("focalLength"),
                "iso": exif.get("iso"),
                "exposureTime": exif.get("exposureTime"),
                "latitude": exif.get("latitude"),
                "longitude": exif.get("longitude"),
                "orientation": exif.get("orientation"),
            },
            raw=payload,
        )

    # ---------- Fetching ----------
    def refresh(self) -> "ImmichAsset":
        """Refetch the asset from API and return a new ImmichAsset (immutable)."""
        data = self.client.get_asset(self.id)
        return ImmichAsset.from_api(self.client, data)

    def get_thumbnail(
        self,
        size: str = "preview",
        save_to: Optional[Path] = None,
        filename: Optional[str] = None,
    ) -> bytes:
        """
        Fetch the thumbnail; optionally save it. Returns bytes.
        """
        data = self.client.get_thumbnail(self.id, size=size, save=False)
        if save_to is not None:
            save_to.mkdir(parents=True, exist_ok=True)
            if not filename:
                filename = f"{self.id}_thumb_{size}.jpg"
            (save_to / filename).write_bytes(data)
        return data

    def stream_original(self) -> requests.Response:
        """
        Return a streaming Response for the original file.
        Caller is responsible for closing/iterating the stream.
        """
        return self.client.stream_original(self.id)

    def download_original(self, out_dir: Path, filename: Optional[str] = None) -> Path:
        """
        Download the original asset to out_dir and return the path.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        name = filename or self.original_file_name or f"{self.id}.bin"
        path = out_dir / name
        with self.stream_original() as r, open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                if chunk:
                    f.write(chunk)
        return path

    # ---------- Tabular / dict helpers ----------
    def to_row(self) -> Dict[str, Any]:
        """One flat dict row similar to your existing _flatten_asset."""
        row = {
            "id": self.id,
            "deviceAssetId": self.device_asset_id,
            "type": self.type,
            "fileCreatedAt": self.file_created_at,
            "fileModifiedAt": self.file_modified_at,
            "originalFileName": self.original_file_name,
            "duration": self.duration,
            "ownerId": self.owner_id,
            "ownerName": self.owner_name,
            "deviceId": self.device_id,
        }
        # Merge exif with "exif." prefix
        for k, v in self.exif.items():
            row[f"exif.{k}"] = v
        return row
    

@dataclass(frozen=True)
class ImmichAlbum:
    """
    A light album model that can iterate assets, paginate, and export to DataFrame.
    """
    client: "ImmichClient"
    id: str
    name: Optional[str] = None
    created_at: Optional[str] = None
    asset_count: Optional[int] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    # ---------- Construction ----------
    @staticmethod
    def from_api(client: "ImmichClient", payload: Dict[str, Any]) -> "ImmichAlbum":
        return ImmichAlbum(
            client=client,
            id=payload.get("id"),
            name=payload.get("albumName"),
            created_at=payload.get("createdAt"),
            asset_count=(payload.get("assetCount") if payload.get("assetCount") is not None else None),
            raw=payload,
        )

    # ---------- Fetch / refresh ----------
    def refresh(self) -> "ImmichAlbum":
        """Refetch album metadata and return a new ImmichAlbum (immutable)."""
        data = self.client.get_album(self.id)
        return ImmichAlbum.from_api(self.client, data)

    # ---------- Assets (unpaginated / paginated) ----------
    def assets(self) -> List[ImmichAsset]:
        """
        Return all album assets as ImmichAsset objects (best effort).
        NOTE: For very large albums, prefer iter_pages.
        """
        raw_assets = self.client.list_album_assets(self.id) or []
        return [ImmichAsset.from_api(self.client, a) for a in raw_assets]

    def iter_pages(self, per_page: int = 48) -> Iterator[List[ImmichAsset]]:
        """
        Iterate assets in pages using the client's robust pagination fallback.
        """
        page = 1
        while True:
            data = self.client.list_album_assets_page(self.id, page=page, per_page=per_page)
            items = data.get("items", [])
            if not items:
                break
            yield [ImmichAsset.from_api(self.client, a) for a in items]
            if len(items) < per_page:
                break
            page += 1

    def page(self, page: int = 1, per_page: int = 48) -> Tuple[List[ImmichAsset], int]:
        """
        Retrieve a single page of assets and the total count.
        """
        data = self.client.list_album_assets_page(self.id, page=page, per_page=per_page)
        items = [ImmichAsset.from_api(self.client, a) for a in data.get("items", [])]
        total = int(data.get("total", 0))
        return items, total

    # ---------- Tabular ----------
    def to_dataframe(self, columns: Optional[List[str]] = None):
        """
        Build a pandas.DataFrame for album assets using the asset rows.
        Requires pandas to be installed.
        """
        if pd is None:
            raise RuntimeError("pandas is not installed. Run: pip install pandas")

        rows = []
        # Prefer paging to limit memory on large albums
        for page_items in self.iter_pages(per_page=200):
            rows.extend(a.to_row() for a in page_items)

        import pandas as _pd
        df = _pd.DataFrame(rows)
        if columns:
            existing = [c for c in columns if c in df.columns]
            df = df[existing]
        return df