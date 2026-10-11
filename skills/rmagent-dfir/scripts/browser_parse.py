#!/usr/bin/env python3
"""browser_parse.py — parse a pulled browser history DB OFFLINE (jump host).

Input must be an ircollect-acquired COPY (collected/<witness>__<file>), never
the live witness path. History/places are sqlite — the witness never runs a
parser; this one runs where the copy landed.

  python3 browser_parse.py collected/ws1__History --out case/browser.json
  python3 browser_parse.py collected/ws1__places.sqlite

Output JSON: {kind, db, rows: [...], holes: [...]}. A table that will not read
is a hole, not zero rows.
"""
from __future__ import annotations
import json, sqlite3, sys
from datetime import datetime, timezone
from pathlib import Path

CHROME_EPOCH = 11644473600  # seconds between 1601-01-01 and 1970-01-01
CHROME_LIMITS = (("urls", "SELECT url,title,visit_count,last_visit_time FROM urls "
                        "ORDER BY last_visit_time DESC LIMIT 300"),
                 ("downloads", "SELECT target_path,start_time,total_bytes,tab_url "
                        "FROM downloads ORDER BY start_time DESC LIMIT 150"))


def _iso(ts: float) -> str | None:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


def _chrome_ts(us) -> str | None:
    if not us:
        return None
    return _iso(us / 1_000_000 - CHROME_EPOCH)


def _open_ro(p: Path) -> sqlite3.Connection:
    # immutable=1: the copy is frozen evidence — never journal, never write.
    return sqlite3.connect(f"file:{p}?mode=ro&immutable=1", uri=True)


def parse_chromium(p: Path) -> dict:
    out = {"kind": "chromium", "db": str(p), "rows": [], "holes": []}
    con = _open_ro(p)
    for label, sql in CHROME_LIMITS:
        try:
            for row in con.execute(sql):
                if label == "urls":
                    url, title, vc, lv = row
                    out["rows"].append({"url": url[:300], "title": (title or "")[:150],
                                        "visits": vc, "last_visit": _chrome_ts(lv)})
                else:
                    tp, st, tb, tu = (row + (None,))[:4]
                    out["rows"].append({"download": tp[:300], "started": _chrome_ts(st),
                                        "bytes": tb, "source_page": (tu or "")[:200]})
        except Exception as e:
            out["holes"].append(f"{label}: {e}")
    con.close()
    return out


def parse_places(p: Path) -> dict:
    out = {"kind": "firefox_places", "db": str(p), "rows": [], "holes": []}
    con = _open_ro(p)
    try:
        sql = ("SELECT url,title,visit_count,last_visit_date FROM moz_places "
               "ORDER BY last_visit_date DESC LIMIT 300")
        for url, title, vc, lv in con.execute(sql):
            ts = _iso(lv / 1_000_000) if lv else None
            out["rows"].append({"url": url[:300], "title": (title or "")[:150],
                                "visits": vc, "last_visit": ts})
    except Exception as e:
        out["holes"].append(f"moz_places: {e}")
    con.close()
    return out


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    src = Path(argv[0])
    if not src.exists():
        print(json.dumps({"error": f"no such file: {src}"}))
        return 2
    name = src.name.lower()
    parser = parse_places if "places" in name else parse_chromium
    try:
        result = parser(src)
    except sqlite3.DatabaseError as e:
        result = {"kind": "unknown", "db": str(src), "rows": [],
                  "holes": [f"not a readable sqlite database: {e}"]}
    out_idx = argv.index("--out") if "--out" in argv else None
    if out_idx is not None:
        Path(argv[out_idx + 1]).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
