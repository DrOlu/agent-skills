#!/usr/bin/env python3
"""ASCII ISO 8583-1987 pack/unpack for the payments ring.

Lab decoder: MTI + primary/secondary bitmap + a useful subset of fields.
Postilion in production may speak EBCDIC, binary length prefixes, or a
private header — ingest.py must strip those before calling unpack().

Field 2 (PAN) is masked on the way *out* of unpack_record(). Packed bytes
exist only in memory during decode; they are never written to the ring.
"""
from __future__ import annotations

from typing import Any

from iso import mask_pan

# (length_or_var, type) — character counts in the ASCII dialect.
# ll / lll = 2- or 3-digit ASCII length prefix then N characters.
FIELDS: dict[int, tuple] = {
    2: ("ll", "n"),      # PAN
    3: (6, "n"),         # processing code
    4: (12, "n"),        # amount
    7: (10, "n"),        # transmission datetime MMDDhhmmss
    11: (6, "n"),        # STAN
    12: (6, "n"),        # local time
    13: (4, "n"),        # local date
    18: (4, "n"),        # MCC
    22: (3, "n"),        # POS entry
    32: ("ll", "n"),     # acquirer id
    37: (12, "an"),      # RRN
    38: (6, "an"),       # auth id
    39: (2, "an"),       # response code
    41: (8, "an"),       # terminal id
    42: (15, "an"),      # card acceptor
    43: (40, "an"),      # acceptor name/location
    49: (3, "n"),        # currency
    54: ("lll", "an"),   # additional amounts
    90: (42, "n"),       # original data
}

MTI_KIND = {
    "0200": "fin_req",
    "0210": "fin_resp",
    "0400": "rev_req",
    "0410": "rev_resp",
    "0420": "rev_adv",
    "0430": "rev_adv_resp",
    "0800": "nmm_req",
    "0810": "nmm_resp",
}


def _bit_on(bitmap: bytes, field: int) -> bool:
    idx = field - 1
    return bool(bitmap[idx // 8] & (0x80 >> (idx % 8)))


def _set_bit(bitmap: bytearray, field: int) -> None:
    idx = field - 1
    bitmap[idx // 8] |= 0x80 >> (idx % 8)


def pack(mti: str, fields: dict[int, str]) -> bytes:
    if len(mti) != 4 or not mti.isdigit():
        raise ValueError(f"bad MTI {mti!r}")
    present = sorted(int(k) for k in fields)
    need_sec = any(f > 64 for f in present)
    bm = bytearray(16 if need_sec else 8)
    if need_sec:
        _set_bit(bm, 1)
    body = bytearray()
    for f in present:
        if f == 1:
            continue
        spec = FIELDS.get(f)
        if spec is None:
            raise ValueError(f"unsupported field {f}")
        val = str(fields[f])
        length, kind = spec
        if length == "ll":
            body += f"{len(val):02d}".encode("ascii") + val.encode("ascii")
        elif length == "lll":
            body += f"{len(val):03d}".encode("ascii") + val.encode("ascii")
        else:
            if len(val) != length:
                val = val.ljust(length)[:length] if kind == "an" else val.zfill(length)[:length]
            body += val.encode("ascii")
        _set_bit(bm, f)
    return mti.encode("ascii") + bytes(bm) + bytes(body)


def unpack(buf: bytes) -> dict[int | str, str]:
    if len(buf) < 12:
        raise ValueError("ISO message too short")
    mti = buf[:4].decode("ascii")
    i = 4
    bm1 = buf[i:i + 8]
    i += 8
    bitmap = bytearray(bm1)
    if _bit_on(bm1, 1):
        if len(buf) < i + 8:
            raise ValueError("missing secondary bitmap")
        bitmap += buf[i:i + 8]
        i += 8
    out: dict[int | str, str] = {"mti": mti}
    max_field = 128 if len(bitmap) == 16 else 64
    for f in range(2, max_field + 1):
        if not _bit_on(bytes(bitmap), f):
            continue
        spec = FIELDS.get(f)
        if spec is None:
            raise ValueError(f"present but unsupported field {f}")
        length, _kind = spec
        if length == "ll":
            n = int(buf[i:i + 2].decode("ascii"))
            i += 2
            out[f] = buf[i:i + n].decode("ascii")
            i += n
        elif length == "lll":
            n = int(buf[i:i + 3].decode("ascii"))
            i += 3
            out[f] = buf[i:i + n].decode("ascii")
            i += n
        else:
            out[f] = buf[i:i + length].decode("ascii")
            i += length
    return out


def unpack_record(buf: bytes, *, tap: str, t: float, src: str = "", dst: str = "") -> dict[str, Any]:
    """Decoded, PAN-masked ring record. This is what hits disk."""
    fields = unpack(buf)
    pan = fields.get(2)
    return {
        "t": t,
        "tap": tap,
        "src": src,
        "dst": dst,
        "mti": fields["mti"],
        "kind": MTI_KIND.get(fields["mti"], "other"),
        "stan": str(fields.get(11, "")).zfill(6) if fields.get(11) else None,
        "rrn": fields.get(37),
        "tid": (fields.get(41) or "").strip() or None,
        "amount": fields.get(4),
        "rc": fields.get(39),
        "proc": fields.get(3),
        "pan_masked": mask_pan(str(pan)) if pan else None,
        "raw_len": len(buf),
    }


def pack_financial(*, mti: str, stan: str, rrn: str, pan: str, amount: str,
                   tid: str, rc: str | None = None, proc: str = "010000") -> bytes:
    """Fixture builder. PAN is an argument only so tests can prove masking."""
    fields = {
        2: "".join(c for c in pan if c.isdigit()),
        3: proc,
        4: amount.zfill(12),
        7: "0908100000",
        11: stan.zfill(6),
        12: "100000",
        13: "0908",
        37: rrn.ljust(12)[:12],
        41: tid.ljust(8)[:8],
        42: "ACQUIRER0000001",
        49: "566",
    }
    if rc is not None:
        fields[39] = rc.ljust(2)[:2]
    return pack(mti, fields)
