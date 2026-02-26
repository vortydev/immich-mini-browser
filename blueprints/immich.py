# blueprints/immich.py
from __future__ import annotations
import json
from pathlib import Path
from flask import Blueprint, Response, request, jsonify, render_template, abort

from config import PER_PAGE, TTL_THUMBS, TTL_META, THUMB_DIR, META_DIR
from app_utils import _album_cover_asset_id, _send_cached_image, _fmt_date
from immich_client import ImmichClient
from immich_cache import ImmichCache

bp = Blueprint("immich", __name__)
client = ImmichClient()
cache = ImmichCache()

@bp.get("/albums")
def albums():
    include_empty = str(request.args.get("include_empty", "0")).lower() in ("1", "true", "yes", "on")

    albums = client.list_albums()
    # Enrich with cover asset ids
    enriched = []
    for a in albums:
        cover_id = _album_cover_asset_id(a)
        if not cover_id:
        # Best-effort: fetch album to inspect assets
            try:
                full = client.get_album(a.get("id"))
                cover_id = _album_cover_asset_id(full)
            except Exception:
                cover_id = None
        enriched.append({
            "id": a.get("id"),
            "name": a.get("albumName"),
            "assetCount": a.get("assetCount"),
            "coverAssetId": cover_id,
            })
        
    shown = enriched if include_empty else [x for x in enriched if (x.get("assetCount") or 0) > 0]

    return render_template(
        "albums.html",
        albums=shown,
        include_empty=include_empty,
        total=len(enriched),
        shown=len(shown),
        hidden=max(0, len(enriched) - len(shown)),
    )

@bp.get("/albums/<album_id>/viewer")
def album_viewer(album_id: str):
    # simple shell; the page will fetch data via JSON + SSE
    try:
        album = client.get_album(album_id)
    except Exception as e:
        abort(404, description=f"Album not found: {e}")
    # default per_page from query or env
    per_page = int(request.args.get("per_page", PER_PAGE))
    return render_template("album_viewer.html", album=album, per_page=per_page)


@bp.get("/api/albums.json")
def api_albums():
    """
    GET /immich/api/albums.json?include_empty=0|1
    Returns albums in the shape your FV /api/media/immich/albums expects.
    """
    include_empty = str(request.args.get("include_empty", "0")).lower() in ("1", "true", "yes", "on")

    try:
        albums = client.list_albums() or []
    except Exception as e:
        return jsonify({"error": str(e), "items": [], "total": 0}), 502

    enriched = []
    for a in albums:
        album_id = a.get("id")
        cover_id = _album_cover_asset_id(a)

        if not cover_id and album_id:
            # best-effort: fetch full album to find a cover/first asset
            try:
                full = client.get_album(album_id)
                cover_id = _album_cover_asset_id(full)
            except Exception:
                cover_id = None

        enriched.append({
            "id": album_id,
            "name": a.get("albumName"),
            "assetCount": a.get("assetCount") or 0,
            "coverAssetId": cover_id,
        })

    shown = enriched if include_empty else [x for x in enriched if (x.get("assetCount") or 0) > 0]

    return jsonify({
        "items": shown,
        "total": len(shown),
        "meta": {
            "include_empty": include_empty,
            "total_all": len(enriched),
            "hidden": max(0, len(enriched) - len(shown)),
        },
    })

@bp.get("/api/albums/<album_id>/assets.json")
def api_album_assets(album_id: str):
    """Returns all assets metadata for an album (no thumbnails)."""
    try:
        raw = client.list_album_assets(album_id) or []
    except Exception as e:
        return jsonify({"error": str(e)}), 502

    items = [{
        "id": a.get("id"),
        "originalFileName": a.get("originalFileName"),
        "fileCreatedAt": _fmt_date(a.get("fileCreatedAt")),
        "type": a.get("type"),
        "description": a.get("description") or a.get("assetInfo", {}).get("description"),
    } for a in raw]

    return jsonify({"items": items, "total": len(items)})

@bp.get("/api/albums/<album_id>/prewarm")
def api_album_prewarm(album_id: str):
    """SSE stream: warms thumbnail cache and reports progress."""
    size = request.args.get("size", "preview")

    def generate():
        try:
            assets = client.list_album_assets(album_id) or []
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
            return

        total = len(assets)
        yield f"event: meta\ndata: {json.dumps({'total': total})}\n\n"

        done = 0
        for a in assets:
            aid = a.get("id")
            try:
                # cache per asset (uses images/ bucket)
                cache.fetch_or_cache(client, aid, kind="images", size=size)
            except Exception:
                pass
            done += 1
            if done % 1 == 0:
                yield f"event: progress\ndata: {json.dumps({'done': done, 'total': total})}\n\n"

        yield "event: complete\ndata: {}\n\n"

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # nginx: disable buffering if present
        "Content-Type": "text/event-stream",
        "Connection": "keep-alive",
    }
    return Response(generate(), headers=headers)

# Thumbnail proxy so we never expose the API key to the browser
# Use cached image thumbnails
@bp.get("/thumb/<asset_id>")
def thumb(asset_id: str):
    size = request.args.get("size", "preview")
    try:
        thumb_path = cache.fetch_or_cache(client, asset_id, kind="images", size=size)
    except Exception as e:
        print(f"An error occured: {e}")
        abort(404, description=str(e))
    return _send_cached_image(thumb_path)

# Use cached album-cover thumbnails (cache by album_id key)
@bp.get("/thumb/album/<album_id>/<asset_id>")
def thumb_album(album_id: str, asset_id: str):
    size = request.args.get("size", "preview")
    try:
        thumb_path = cache.fetch_or_cache(
            client, asset_id, kind="albums", key=album_id, size=size
        )
    except Exception as e:
        print(f"An error occured: {e}")
        abort(404, description=str(e))
    return _send_cached_image(thumb_path)

@bp.get("/full/<asset_id>")
def full_original(asset_id: str):
    """Stream the original file for a given asset id."""
    try:
        r = client.stream_original(asset_id)  # requests.Response (stream=True)
    except Exception as e:
        # Keep 404 semantics visible to the browser; your lightbox already falls back to preview
        abort(404, description=f"Original not available: {e}")

    # Propagate useful headers from Immich
    content_type = r.headers.get("Content-Type", "application/octet-stream")
    content_len = r.headers.get("Content-Length")
    disp = r.headers.get("Content-Disposition")  # usually inline; fine to pass through

    def generate():
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                yield chunk

    headers = {
        "Content-Type": content_type,
        "Cache-Control": "private, max-age=31536000",
    }
    if content_len:
        headers["Content-Length"] = content_len
    if disp:
        headers["Content-Disposition"] = disp  # keeps filename if Immich provides it

    return Response(generate(), headers=headers)

@bp.route("/api/assets.json", methods=["GET", "POST"])
def api_assets_by_ids():
    """
    Fetch minimal metadata for a list of Immich asset ids.

    GET  /immich/api/assets.json?ids=a,b,c
    POST /immich/api/assets.json {"ids":["a","b","c"]}
    """
    ids: list[str] = []

    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        raw = payload.get("ids") or []
        if isinstance(raw, str):
            raw = [x.strip() for x in raw.split(",")]
        if isinstance(raw, list):
            ids = [str(x).strip() for x in raw if str(x).strip()]
    else:
        # supports ?ids=a,b,c and ?ids=a&ids=b
        raw_list = request.args.getlist("ids")
        if len(raw_list) == 1 and "," in (raw_list[0] or ""):
            raw_list = [x.strip() for x in raw_list[0].split(",")]
        ids = [str(x).strip() for x in raw_list if str(x).strip()]

    # de-dupe while preserving order
    seen = set()
    ids = [x for x in ids if not (x in seen or seen.add(x))]

    if not ids:
        return jsonify({"items": [], "total": 0})

    items = []
    for aid in ids:
        try:
            a = client.get_asset(aid)

            desc = a.get("description")
            if desc is None and isinstance(a.get("exifInfo"), dict):
                desc = a["exifInfo"].get("description")
        except Exception:
            # best-effort: keep placeholder so UI can show "missing"
            items.append({"id": aid, "missing": True})
            continue

        items.append({
            "id": a.get("id") or aid,
            "originalFileName": a.get("originalFileName"),
            "fileCreatedAt": _fmt_date(a.get("fileCreatedAt")),
            "type": a.get("type"),
            # helpful for the UI (thumb + full)
            "thumbUrl": f"/immich/thumb/{aid}?size=preview",
            "fullUrl": f"/immich/full/{aid}",
            "description": desc,
        })

    return jsonify({"items": items, "total": len(items)})

@bp.get("/cache")
def admin_cache():
    return render_template("immich_cache.html")

def _meta_file_stats() -> dict:
    root = Path(META_DIR)
    files = 0
    total_bytes = 0
    if root.exists():
        for p in root.glob("*.json"):
            if p.is_file():
                files += 1
                try:
                    total_bytes += p.stat().st_size
                except FileNotFoundError:
                    pass
    return {"files": files, "bytes": total_bytes, "path": str(root)}

@bp.get("/api/cache/stats.json")
def api_admin_cache_stats():
    thumbs = cache.count_cached()  # albums/images + totals
    meta = _meta_file_stats()
    return jsonify({
        "thumbs": thumbs,
        "meta": meta,
        "ttl": {"thumbs": TTL_THUMBS, "meta": TTL_META},
        "paths": {"thumbs": str(THUMB_DIR), "meta": str(META_DIR)},
    })

@bp.post("/api/cache/clear-thumbs.json")
def api_admin_cache_clear_thumbs():
    payload = request.get_json(silent=True) or {}
    kind = (payload.get("kind") or "").strip().lower() or None  # None | albums | images
    if kind not in (None, "albums", "images"):
        return jsonify({"error": "kind must be null, 'albums', or 'images'"}), 400
    removed = cache.clear_cache(kind)
    return jsonify({"ok": True, "removed": removed, "kind": kind})

@bp.post("/api/cache/clear-meta.json")
def api_admin_cache_clear_meta():
    removed = cache.clear_all_meta()
    return jsonify({"ok": True, "removed": removed})

@bp.post("/api/cache/refresh-albums.json")
def api_admin_cache_refresh_albums():
    try:
        albums = cache.get_or_fetch_albums(client, force=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "total": len(albums)})

@bp.post("/api/cache/refresh-album-assets.json")
def api_admin_cache_refresh_album_assets():
    payload = request.get_json(silent=True) or {}
    album_id = (payload.get("album_id") or "").strip()
    if not album_id:
        return jsonify({"error": "album_id is required"}), 400
    try:
        assets = cache.get_or_fetch_album_assets(client, album_id, force=True)
    except Exception as e:
        return jsonify({"error": str(e)}), 502
    return jsonify({"ok": True, "album_id": album_id, "total": len(assets)})
