#!/usr/bin/env python3
"""amcache_parse.py — parse an ircollect-acquired Amcache.hve OFFLINE.

Input must be a pulled COPY (dfir.py collect), never the live hive, and the
hive is never loaded or parsed on the witness.

  python3 amcache_parse.py collected/ws1__Amcache.hve --out case/amcache.json

Tolerant pure-Python regf reader: indexes hbin cells, walks nk/vk records from
the root, then reports:
  - InventoryApplication* entries (string values: path, publisher, versions)
  - FileOrKey entries (key last-write time + a tolerant read of the 'f' blob)
Formats vary by Windows build; anything unrecognized is a HOLE with its reason
— never a guess. A corrupt hive is a hole, not zero entries.
"""
from __future__ import annotations
import json, struct, sys
from datetime import datetime, timezone
from pathlib import Path

MAX_ENTRIES = 400
MAX_STR_VAL = 160
MAX_STRS_PER_ENTRY = 12


def _ft(u64: int) -> str | None:
    if not u64:
        return None
    try:
        return datetime.fromtimestamp(u64 / 10_000_000 - 11644473600, tz=timezone.utc)\
            .strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return None


class RegfError(Exception):
    pass


def _cells(buf: bytes) -> dict:
    """Index every allocated cell: {absolute data offset: cell bytes}."""
    if buf[:4] != b"regf":
        raise RegfError("not a regf hive (bad magic)")
    root_rel = struct.unpack_from("<I", buf, 0x24)[0]
    total = struct.unpack_from("<I", buf, 0x28)[0]
    cells, pos = {}, 0x1000
    end = min(len(buf), 0x1000 + total)
    while pos + 0x20 <= end:
        if buf[pos:pos + 4] != b"hbin":
            raise RegfError(f"bad hbin signature at 0x{pos:x}")
        span = struct.unpack_from("<I", buf, pos + 8)[0]
        if span < 0x20:
            raise RegfError(f"bad hbin span at 0x{pos:x}")
        cpos = pos + 0x20
        while cpos + 4 <= pos + span and cpos < end:
            size = struct.unpack_from("<i", buf, cpos)[0]
            if size == 0:
                break
            if size < 0 and cpos + abs(size) <= end:   # allocated; free cells just skip
                cells[cpos + 4] = buf[cpos + 4: cpos + abs(size)]
            cpos += abs(size)
        pos += span
    root = 0x1000 + root_rel
    if root not in cells and (root + 4) in cells:
        root += 4   # some hives reference the cell's size field, not its data
    return cells, root


def _name(raw: bytes, utf16: bool) -> str:
    try:
        return (raw.decode("utf-16-le") if utf16 else raw.decode("latin-1")).rstrip("\x00")
    except UnicodeDecodeError:
        return raw.decode("latin-1", "replace")


def _keyname(raw: bytes, utf16: bool) -> str:
    """Name decode with the misread heuristic: some nk records store ASCII
    bytes without the 0x0004 flag — pure-ASCII bytes that decode to CJK are
    re-read as latin-1. A genuine UTF-16 name (zero bytes present) is untouched."""
    if not raw:
        return ""
    if utf16:
        s = raw.decode("utf-16-le", "replace")
        if b"\x00" not in raw and any(0x2E80 <= ord(c) <= 0x9FFF for c in s):
            s = raw.decode("latin-1")
        return s.rstrip("\x00")
    return raw.decode("latin-1").rstrip("\x00")


def _cell(cells: dict, ref: int):
    """Resolve a cell reference to (absolute_data_offset, bytes), or (None, None).
    Real hives disagree: refs are bin-relative (base 0x1000) or absolute, and
    point at the data or at the cell's size field. Try each, prefer exact."""
    for cand in (ref + 0x1000, ref + 0x1004, ref, ref + 4):
        if cand in cells:
            return cand, cells[cand]
    return None, None


class NK:
    __slots__ = ("name", "timestamp", "subkeys_off", "nvalues", "values_off", "off")

    def __init__(self, off: int, data: bytes):
        self.off = off
        flags = struct.unpack_from("<H", data, 2)[0]
        nlen = struct.unpack_from("<H", data, 0x48)[0]
        self.name = _keyname(data[0x4C:0x4C + nlen], not (flags & 0x0004))  # 0x0004 = ASCII name
        self.timestamp = struct.unpack_from("<Q", data, 4)[0]
        self.subkeys_off = struct.unpack_from("<I", data, 0x1C)[0]
        self.nvalues = struct.unpack_from("<I", data, 0x24)[0]
        self.values_off = struct.unpack_from("<I", data, 0x28)[0]


def _subkeys(cells: dict, nk: NK) -> list:
    out, seen = [], set()
    lists = [nk.subkeys_off]
    while lists:
        ref = lists.pop(0)
        off, rec = _cell(cells, ref) if ref else (None, None)
        if not ref or off in seen or not rec:
            continue
        seen.add(off)
        if rec[:2] == b"ri":
            for i in range(struct.unpack_from("<H", rec, 2)[0]):
                lists.append(struct.unpack_from("<I", rec, 4 + 4 * i)[0])
            continue
        d = rec[4:]  # lf/lh entries start after sig(2)+count(2)
        count = struct.unpack_from("<H", rec, 2)[0]
        for i in range(count):
            if len(d) < 8 * i + 4:
                break
            so = struct.unpack_from("<I", d, 8 * i)[0]
            soff, sub = _cell(cells, so) if so else (None, None)
            if sub and sub[:2] == b"nk":
                try:
                    out.append(NK(soff, sub))
                except struct.error:
                    continue
    return out


def _values(cells: dict, nk: NK) -> dict:
    vals = {}
    if not nk.nvalues:
        return vals
    loff, lst = _cell(cells, nk.values_off)
    if not lst:
        return vals
    for i in range(min(nk.nvalues, 64)):
        try:
            vo = struct.unpack_from("<I", lst, 4 * i)[0]
        except struct.error:
            break
        _, d = _cell(cells, vo) if vo else (None, None)
        if not d or d[:2] != b"vk":
            continue
        try:
            nlen = struct.unpack_from("<H", d, 2)[0]
            vname = _keyname(d[0x14:0x14 + nlen], True)
            f4 = struct.unpack_from("<I", d, 4)[0]
            f8 = struct.unpack_from("<I", d, 8)[0]
            fc = struct.unpack_from("<I", d, 0xC)[0]
            dlen = struct.unpack_from("<I", d, 0x10)[0]
        except struct.error:
            continue
        # Two vk layouts are in the wild, told apart by the type field (always
        # small): classic — doff@4, type@8, flags@0xC, dlen@0x10; modern
        # Win8.1+ — dlen@4, doff@8, type@0xC (verified against a live
        # Server-2022 Amcache: dlen 0x3C = exactly the UTF-16 path length).
        if f8 <= 0x20:                       # classic
            doff, dtype, flags = f4, f8, fc & 0xFFFF
            data = b""
            if dlen == 0:
                pass
            elif dlen <= 4:
                data = struct.pack("<I", doff)[:dlen]
            elif dlen & 0x80000000:
                data = struct.pack("<I", doff)[:dlen & 0x7FFFFFFF]
            else:
                _, blob = _cell(cells, doff)
                if blob:
                    data = blob[:dlen]
        else:                                # modern: dlen@4, doff@8
            dtype, dlen = fc, f4
            data = b""
            if dlen == 0:
                pass
            elif dlen <= 4:
                data = struct.pack("<I", f8)[:dlen]
            else:
                _, blob = _cell(cells, f8)
                if blob:
                    data = blob[:dlen]
        vals[vname] = (dtype, data)
    return vals


def _strings_in(blob: bytes, limit: int = 3) -> list:
    out, run, i = [], [], 0
    while i + 1 < len(blob) and len(out) < limit:
        ch = int.from_bytes(blob[i:i + 2], "little")
        if 0x20 <= ch < 0x7F:
            run.append(chr(ch))
        else:
            if len(run) >= 6:
                out.append("".join(run)[:MAX_STR_VAL])
            run = []
        i += 2
    if len(run) >= 6 and len(out) < limit:
        out.append("".join(run)[:MAX_STR_VAL])
    return out


def parse(buf: bytes) -> dict:
    try:
        cells, root_off = _cells(buf)
        root = NK(root_off, cells[root_off])
    except (RegfError, struct.error, KeyError, IndexError) as e:
        return {"kind": "amcache", "entries_app": [], "entries_fileorkey": [],
                "holes": [f"regf parse failed: {e}"]}
    holes = []
    root = NK(root_off, cells[root_off])
    # Amcache nests under Root\Root (some builds name the hive root 'Root' too)
    node = root
    for child in _subkeys(cells, root):
        if child.name.lower() == "root":
            node = child
            break
    out = {"kind": "amcache", "entries_app": [], "entries_fileorkey": [], "holes": holes}
    for fam in _subkeys(cells, node):
        f = fam.name.lower()
        if f.startswith("inventoryapplicationfile") or f == "inventoryapplication":
            for e in _subkeys(cells, fam)[:MAX_ENTRIES]:
                rec = {"name": e.name[:200], "key_write": _ft(e.timestamp)}
                for vn, (vt, vd) in _values(cells, e).items():
                    if vt in (1, 2) and vd and len(rec) <= MAX_STRS_PER_ENTRY:
                        rec[vn[:40].lower().replace(" ", "_")] = _name(vd, True)[:MAX_STR_VAL]
                out["entries_app"].append(rec)
        elif f == "fileorkey":
            for e in _subkeys(cells, fam)[:MAX_ENTRIES]:
                rec = {"name": e.name[:200], "key_write": _ft(e.timestamp)}
                for vn, (vt, vd) in _values(cells, e).items():
                    if vn == "f":
                        rec["f_size"] = len(vd)
                        if len(vd) >= 4:
                            rec["f_version"] = f"0x{struct.unpack_from('<I', vd, 0)[0]:x}"
                        rec["f_strings"] = _strings_in(vd)
                out["entries_fileorkey"].append(rec)
    if not out["entries_app"] and not out["entries_fileorkey"]:
        holes.append("no FileOrKey/InventoryApplication* under the hive root — "
                     "format variant or not an Amcache hive")
    return out


def _placeholder(buf: bytes):  # kept for callers that want (cells, root) directly
    return _cells(buf)


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    src = Path(argv[0])
    if not src.exists():
        print(json.dumps({"error": f"no such file: {src}"}))
        return 2
    try:
        result = parse(src.read_bytes())
    except (RegfError, struct.error, KeyError) as e:
        result = {"kind": "amcache", "rows": [], "holes": [f"regf parse failed: {e}"]}
    if "--out" in argv:
        i = argv.index("--out")
        Path(argv[i + 1]).write_text(json.dumps(result, indent=1))
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
