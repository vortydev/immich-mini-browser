# catalog_inspector.py
from __future__ import annotations
import json, argparse, sys, os, re
from collections import Counter, defaultdict
from typing import Any, Optional, List, Dict
from datetime import datetime

try:
    # Prefer rich if available
    from rich.console import Console
    from rich.json import JSON as RichJSON
    _HAS_RICH = True
    _RICH_CONSOLE = Console()
except Exception:
    _HAS_RICH = False

# Import your stores
from stores import character_store as CS
from stores import render_store as RS

# ---- colored JSON pretty printer ----
RESET = "\x1b[0m"
K = "\x1b[34;1m"        # keys (bright blue)
S = "\x1b[32m"          # strings (normal green)
N = "\x1b[33;1m"        # numbers (bright yellow)
B = "\x1b[35;1m"        # booleans (bright magenta)
NL = "\x1b[3;31m"       # null (italic + red)
P = "\x1b[38;5;245m"    # punctuation (gray)
D = "\x1b[36;1m"        # dates (bright cyan)

_ISO_DT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}"                                  # YYYY-MM-DD
    r"(?:[ T]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"              #  HH:MM:SS(.us)
    r"(?:Z|[+-]\d{2}:\d{2})?)?$"                           #  Z or +HH:MM (optional)
)

def _is_date_like(s: str) -> bool:
    if _ISO_DT_RE.match(s):
        return True
    # final safety: try parsing (handles space/T, with/without tz, with Z)
    try:
        z = s.replace("Z", "+00:00")
        datetime.fromisoformat(z if "T" in z or " " in z else z + " 00:00:00")
        return True
    except Exception:
        return False

def _dump_color(val: Any, indent: int = 0, step: int = 2) -> str:
    pad = " " * (indent * step)
    if isinstance(val, dict):
        if not val:
            return f"{P}{{}}{RESET}"
        lines = [f"{P}{{{RESET}"]
        items = list(val.items())
        for i, (k, v) in enumerate(items):
            sep = "," if i < len(items) - 1 else ""
            key = json.dumps(k, ensure_ascii=False)
            lines.append(
                f"{pad}{' ' * step}{K}{key}{RESET}{P}:{RESET} {_dump_color(v, indent+1, step)}{P}{sep}{RESET}"
            )
        lines.append(f"{pad}{P}}}{RESET}")
        return "\n".join(lines)
    if isinstance(val, list):
        if not val:
            return f"{P}[]{RESET}"
        lines = [f"{P}[{RESET}"]
        for i, v in enumerate(val):
            sep = "," if i < len(val) - 1 else ""
            lines.append(f"{pad}{' ' * step}{_dump_color(v, indent+1, step)}{P}{sep}{RESET}")
        lines.append(f"{pad}{P}]{RESET}")
        return "\n".join(lines)
    if isinstance(val, str):
        text = json.dumps(val, ensure_ascii=False)
        return f"{D if _is_date_like(val) else S}{text}{RESET}"
    if isinstance(val, (int, float)):
        return f"{N}{json.dumps(val, ensure_ascii=False)}{RESET}"
    if isinstance(val, bool):
        return f"{B}{'true' if val else 'false'}{RESET}"
    if val is None:
        return f"{NL}null{RESET}"
    return f"{S}{json.dumps(str(val), ensure_ascii=False)}{RESET}"

def _print_json(obj: Any, pretty: bool = True) -> None:
    """
    If pretty=True  -> always pretty + colored
    If pretty=False -> compact, no color
    """
    if not pretty:
        print(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        return

    # Pretty + colored
    print(_dump_color(obj))
        

def _parse_dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        # Handle ...Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


class CatalogInspector:
    """Utility over character_store and render_store with stats & filters."""

    # ---------- Raw loads ----------
    def characters_json(self) -> Dict[str, Any]:
        # Keep the on-disk shape (schema + characters) for a full dump
        if not CS.CHAR_PATH.exists():
            return {"schema": 1, "characters": {}}
        return json.loads(CS.CHAR_PATH.read_text(encoding="utf-8"))

    def renders_json(self) -> Dict[str, Any]:
        return RS.load_index()

    # ---------- Lookups ----------
    def list_characters(self) -> List[dict]:
        return CS.list_characters()

    def get_character(self, slug: str) -> Optional[dict]:
        return CS.get_character(slug)

    def list_renders(self) -> List[dict]:
        return RS.list_all()

    def get_render(self, render_id: str) -> Optional[dict]:
        return RS.get(render_id)

    def filter_renders(
        self,
        by_character: Optional[str] = None,
        by_album: Optional[str] = None,
        by_tag: Optional[str] = None,
    ) -> List[dict]:
        items = self.list_renders()
        if by_character:
            items = [r for r in items if (r.get("character") or "").lower() == by_character.lower()]
        if by_album:
            items = [r for r in items if (r.get("immich_album_id") or "") == by_album]
        if by_tag:
            t = by_tag.lower()
            items = [r for r in items if any((x or "").lower() == t for x in r.get("tags", []))]
        return items

    # ---------- Stats / Highlights ----------
    def characters_stats(self) -> Dict[str, Any]:
        chars = {c["slug"]: c for c in self.list_characters()}
        renders = self.list_renders()

        renders_per_char = Counter(r.get("character") or "" for r in renders)
        known = {slug for slug in chars.keys()}
        unknown_in_renders = {k for k in renders_per_char.keys() if k and k not in known}

        missing = {
            "missing_name": [s for s, c in chars.items() if not c.get("name")],
            "missing_bio": [s for s, c in chars.items() if not c.get("bio")],
            "missing_appearance": [s for s, c in chars.items() if not c.get("appearance")],
        }

        top = renders_per_char.most_common(10)

        return {
            "total_characters": len(chars),
            "slugs": sorted(chars.keys()),
            "renders_per_character_top10": top,
            "characters_missing_fields": missing,
            "unknown_characters_referenced_in_renders": sorted(unknown_in_renders),
        }

    def renders_stats(self) -> Dict[str, Any]:
        items = self.list_renders()
        total = len(items)

        by_character = Counter(r.get("character") or "(none)" for r in items)
        by_album = Counter(r.get("immich_album_id") or "(none)" for r in items)
        by_outfit = Counter(r.get("outfit") or "(none)" for r in items)
        ratings = Counter(r.get("rating") or 0 for r in items)

        # Tag aggregation
        tags = Counter()
        for r in items:
            for t in (r.get("tags") or []):
                if t:
                    tags[t.lower()] += 1

        # Missing fields audit
        missing = defaultdict(int)
        for r in items:
            for k in ("character", "form", "outfit", "title", "rating", "tags", "immich_album_id", "file_created_at"):
                v = r.get(k)
                if v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, list) and not v):
                    missing[k] += 1

        # Date range from file_created_at (when present)
        dts = [_parse_dt(r.get("file_created_at")) for r in items]
        dts = [d for d in dts if d]
        date_range = None
        if dts:
            date_range = {"min": min(dts).isoformat(), "max": max(dts).isoformat()}

        # Latest N by created_at (fallback to missing at end)
        latest = sorted(
            items,
            key=lambda r: (_parse_dt(r.get("file_created_at")) or datetime.min),
            reverse=True,
        )[:10]

        return {
            "total_renders": total,
            "by_character_top10": by_character.most_common(10),
            "by_album_top10": by_album.most_common(10),
            "by_outfit_top10": by_outfit.most_common(10),
            "ratings_distribution": dict(sorted(ratings.items())),
            "top_tags": tags.most_common(20),
            "missing_field_counts": dict(missing),
            "file_created_at_range": date_range,
            "latest_samples": latest,
        }


# ---------------------- CLI ----------------------
def make_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="catalog_inspector",
        description="Inspect characters.json and renders/index.json",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # characters
    pc = sub.add_parser("characters", help="Dump characters or show stats")
    pc.add_argument("--json", action="store_true", help="Print raw characters.json")
    pc.add_argument("--stats", action="store_true", help="Print character stats/highlights")
    pc.add_argument("--slug", help="Print a single character by slug")
    pc.add_argument("--pretty", action="store_true", help="Pretty print JSON output")

    # renders
    pr = sub.add_parser("renders", help="Dump renders or show stats")
    pr.add_argument("--json", action="store_true", help="Print raw renders/index.json")
    pr.add_argument("--stats", action="store_true", help="Print render stats/highlights")
    pr.add_argument("--id", help="Print a single render by id")
    pr.add_argument("--by-character", help="Filter renders by character slug")
    pr.add_argument("--by-album", help="Filter renders by Immich album id")
    pr.add_argument("--by-tag", help="Filter renders by tag (case-insensitive)")
    pr.add_argument("--limit", type=int, default=0, help="Limit rows when printing filtered renders")
    pr.add_argument("--pretty", action="store_true", help="Pretty print JSON output")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = make_parser().parse_args(argv)
    ci = CatalogInspector()

    if args.cmd == "characters":
        if args.slug:
            obj = ci.get_character(args.slug)
            _print_json(obj if obj is not None else {"error": "not found"}, pretty=args.pretty)
            return 0
        if args.stats:
            _print_json(ci.characters_stats(), pretty=True)
            return 0
        if args.json:
            _print_json(ci.characters_json(), pretty=args.pretty or True)
            return 0
        # default: list slugs
        _print_json({"slugs": [c["slug"] for c in ci.list_characters()]}, pretty=True)
        return 0

    if args.cmd == "renders":
        if args.id:
            obj = ci.get_render(args.id)
            _print_json(obj if obj is not None else {"error": "not found"}, pretty=args.pretty)
            return 0
        if args.stats:
            _print_json(ci.renders_stats(), pretty=True)
            return 0
        if args.json:
            _print_json(ci.renders_json(), pretty=args.pretty or True)
            return 0
        # filtered listing
        rows = ci.filter_renders(args.by_character, args.by_album, args.by_tag)
        if args.limit and args.limit > 0:
            rows = rows[: args.limit]
        _print_json(rows, pretty=args.pretty or True)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
