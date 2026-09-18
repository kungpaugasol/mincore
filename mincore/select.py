"""select.py — cost-based encoder selection.

Given a column of values, sample the front of it, run every applicable
encoder, and return the name of the one with the smallest output. The
container stores the chosen encoder name so
that decode can dispatch by lookup.

Design notes:
  - Encoders that raise are silently skipped. A buggy encoder doesn't
    kill the whole pipeline; it should just lose the selection.
  - The default sample size is min(10%, 10_000, len(values)). Small enough
    to be cheap on huge columns, large enough to be representative.
"""

from __future__ import annotations

from mincore.encoders import REGISTRY, ENC_NAMES

SAMPLE_FRACTION = 0.10
SAMPLE_MIN = 1000
SAMPLE_MAX = 10_000


def _sample(values: list) -> list:
    n = len(values)
    k = max(SAMPLE_MIN, min(SAMPLE_MAX, int(n * SAMPLE_FRACTION)))
    return values[:min(k, n)]


def select_encoder(values: list) -> str:
    """Return the name of the cheapest applicable encoder for `values`."""
    if not values:
        return "varint"  # arbitrary; empty columns encode to nothing

    sample = _sample(values)
    best_name = None
    best_size = None

    for name in ENC_NAMES:                        # deterministic order
        enc_fn, _dec_fn, applies = REGISTRY[name]
        if not applies(sample):
            continue
        try:
            size = len(enc_fn(sample))
        except Exception:
            continue
        if best_size is None or size < best_size:
            best_size = size
            best_name = name

    if best_name is None:
        # nothing applicable: fall back to varint (universal)
        return "varint"
    return best_name
