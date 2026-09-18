"""pipeline.py — registry-driven pipeline.

This replaces the Phase 1 hardcoded pipeline. Every column goes through
select_encoder, which samples the column and picks the cheapest applicable
encoder. The chosen encoder is stored in the container header, so decode
dispatches by tag lookup.

Schema-specific handling:
  - Volume is stored as scaled integers (×1e8) to enable DoD. Future updates will eventually push
    this into the encoder itself (i.e. an 'int_scaled' wrapper) but for now
    the pipeline handles it.
"""

from __future__ import annotations

import io

from mincore.container import (
    Column, T_INT, T_FLOAT, T_STR,
    _write_container_to_fileobj, _read_container_from_fileobj,
)
from mincore.encoders import REGISTRY, ENC_NAMES
from mincore.select import select_encoder


#The registry doesn't need this,
#the container does for self-description.
_SCHEMA_TYPES = {
    "timestamp": T_INT,
    "open":      T_FLOAT,
    "high":      T_FLOAT,
    "low":       T_FLOAT,
    "close":     T_FLOAT,
    "volume":    T_FLOAT,   # declared float; encoded as scaled int internally
    "symbol":    T_STR,
}


def _scaled_volume(rows: list[dict]) -> list[int]:
    """Volume × 1e8 as ints, so DoD/varint can operate on it."""
    return [int(round(r["volume"] * 1e8)) for r in rows]


def encode_ohlcv(rows: list[dict], symbols: list[str] | None = None) -> bytes:
    if not rows:
        raise ValueError("no rows")

    n = len(rows)
    cols: list[Column] = []

    # core OHLCV columns
    for name in ("timestamp", "open", "high", "low", "close"):
        vals = [r[name] for r in rows]
        enc_name = select_encoder(vals)
        enc_fn, _, _ = REGISTRY[enc_name]
        cols.append(Column(name, _SCHEMA_TYPES[name], ENC_NAMES.index(enc_name), enc_fn(vals)))

    # volume — scaled int treatment
    vol_int = _scaled_volume(rows)
    enc_name = select_encoder(vol_int)
    enc_fn, _, _ = REGISTRY[enc_name]
    cols.append(Column("volume", T_INT, ENC_NAMES.index(enc_name), enc_fn(vol_int)))

    # optional symbol column
    if symbols is not None:
        assert len(symbols) == n
        enc_name = select_encoder(symbols)
        enc_fn, _, _ = REGISTRY[enc_name]
        cols.append(Column("symbol", T_STR, ENC_NAMES.index(enc_name), enc_fn(symbols)))

    buf = io.BytesIO()
    _write_container_to_fileobj(cols, n, buf)
    return buf.getvalue()


def decode_ohlcv(data: bytes) -> tuple[int, dict[str, list]]:
    buf = io.BytesIO(data)
    row_count, cols = _read_container_from_fileobj(buf)

    out: dict[str, list] = {}
    for c in cols:
        enc_name = ENC_NAMES[c.enc_tag]
        _, dec_fn, _ = REGISTRY[enc_name]
        out[c.name] = dec_fn(c.payload, row_count)

    # undid the preciously used volume scale hack
    if "volume" in out:
        out["volume"] = [v / 1e8 for v in out["volume"]]

    return row_count, out
