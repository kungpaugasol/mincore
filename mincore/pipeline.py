"""pipeline.py — the Phase 1 fixed pipeline. Superseded by select.py in Phase 2.

This exists to prove the encoders work end-to-end on real data. Once Phase 2
lands, this module is dead code and can be deleted. Until then, it's the only
thing that knows about column names — encoders themselves know nothing.
"""

from __future__ import annotations

from mincore.encoders import (
    encode_dod, encode_gorilla, encode_dict, encode_varint,
)
from mincore.container import Column, write_container, read_container, T_INT, T_FLOAT, T_STR

# local tag numbering for the fixed pipeline; Phase 2 replaces this with a registry
_TAG = {"dod": 0, "gorilla": 1, "dict": 2, "varint": 3}


def encode_ohlcv(rows: list[dict], symbols: list[str] | None = None) -> bytes:
    """Encode a list of OHLCV rows into a container. `symbols[i]` labels rows[i]
    if provided; otherwise symbol column is omitted."""
    if not rows:
        raise ValueError("no rows")

    n = len(rows)
    cols: list[Column] = []

    ts = [r["timestamp"] for r in rows]
    cols.append(Column("timestamp", T_INT, _TAG["dod"], encode_dod(ts)))

    for name in ("open", "high", "low", "close"):
        vals = [r[name] for r in rows]
        cols.append(Column(name, T_FLOAT, _TAG["gorilla"], encode_gorilla(vals)))

    vol = [int(round(r["volume"] * 1e8)) for r in rows]
    cols.append(Column("volume", T_INT, _TAG["dod"], encode_dod(vol)))

    if symbols is not None:
        assert len(symbols) == n
        cols.append(Column("symbol", T_STR, _TAG["dict"], encode_dict(symbols)))

    # write_container expects a path; for benchmarking we want bytes.
    # Simplest: write to a temp buffer using a BytesIO-compatible variant.
    import io
    from mincore.container import _write_container_to_fileobj
    buf = io.BytesIO()
    _write_container_to_fileobj(cols, n, buf)
    return buf.getvalue()


def decode_ohlcv(data: bytes) -> tuple[int, dict[str, list]]:
    import io
    from mincore.container import _read_container_from_fileobj
    buf = io.BytesIO(data)
    row_count, cols = _read_container_from_fileobj(buf)
    out: dict[str, list] = {}
    for c in cols:
        if c.enc_tag == _TAG["dod"]:
            from mincore.encoders import decode_dod
            out[c.name] = decode_dod(c.payload, row_count)
        elif c.enc_tag == _TAG["gorilla"]:
            from mincore.encoders import decode_gorilla
            out[c.name] = decode_gorilla(c.payload, row_count)
        elif c.enc_tag == _TAG["dict"]:
            from mincore.encoders import decode_dict
            out[c.name] = decode_dict(c.payload, row_count)
        elif c.enc_tag == _TAG["varint"]:
            from mincore.encoders import decode_varint
            out[c.name] = decode_varint(c.payload, row_count)
        else:
            raise ValueError(f"unknown enc_tag {c.enc_tag}")

    # Volume was stored as scaled integers (×1e8) to enable DoD.
    # Undo the scale to return floats, matching the original loader output.
    if "volume" in out:
        out["volume"] = [v / 1e8 for v in out["volume"]]

    return row_count, out
