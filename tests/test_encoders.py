import random
import math

from mincore.encoders import encode_varint, decode_varint
from mincore.encoders import encode_dod, decode_dod
from mincore.encoders import encode_gorilla, decode_gorilla

def test_varint_roundtrip_small():
    values = [0, 1, -1, 2, -2, 127, 128, -128, -129]
    assert decode_varint(encode_varint(values), len(values)) == values


def test_varint_roundtrip_random():
    random.seed(1)
    for _ in range(50):
        values = [random.randint(-(1 << 40), 1 << 40) for _ in range(200)]
        assert decode_varint(encode_varint(values), len(values)) == values


def test_varint_empty():
    assert encode_varint([]) == b""
    assert decode_varint(b"", 0) == []


def test_varint_zigzag_size():
    # small magnitudes must cost 1 byte
    assert len(encode_varint([0])) == 1
    assert len(encode_varint([1])) == 1
    assert len(encode_varint([-1])) == 1
    assert len(encode_varint([63])) == 1
    assert len(encode_varint([-64])) == 1
    # crossing the 7-bit boundary costs 2
    assert len(encode_varint([64])) == 2
    assert len(encode_varint([-65])) == 2

def test_dod_perfectly_even():
    # classic case: constant 60s spacing
    ts = [1_754_006_400_000 + i * 60_000 for i in range(1000)]
    enc = encode_dod(ts)
    dec = decode_dod(enc, len(ts))
    assert dec == ts
    # should be tiny: ~7 bits/row = ~875 bytes for 1000 rows
    assert len(enc) < 1000, f"dod encoded {len(enc)} bytes for 1000 even rows"


def test_dod_with_gaps():
    ts = [0]
    for i in range(999):
        step = 60_000 if i % 100 else 60_500   # occasional 500ms drift
        ts.append(ts[-1] + step)
    assert decode_dod(encode_dod(ts), len(ts)) == ts


def test_dod_short_sequence():
    # < 2 values falls back to varint
    assert decode_dod(encode_dod([42]), 1) == [42]
    assert decode_dod(encode_dod([]), 0) == []

def test_gorilla_roundtrip_exact():
    # exact float bits must survive
    values = [1.0, 1.0, 1.0, 1.1, 1.1, 1.1000001, 1.2, 1.2]
    dec = decode_gorilla(encode_gorilla(values), len(values))
    assert dec == values


def test_gorilla_smooth_series():
    # realistic price-like series: small ABSOLUTE jitter around a slow trend
    random.seed(42)
    values = [100_000.0]
    for i in range(999):
        values.append(values[-1] + 2.0 * math.sin(i / 10) + random.gauss(0, 0.5))
    enc = encode_gorilla(values)
    dec = decode_gorilla(enc, len(values))
    assert dec == values
    # Realistic financial floats compress to ~5-6 bytes/value under Gorilla.
    # The Gorilla paper's 1.4 bytes/value is for tightly-clustered TSDB metrics,
    # not financial prices. Assert the actual property: Gorilla beats raw 8 bytes/value.
    assert len(enc) < len(values) * 7, f"gorilla used {len(enc)} bytes for {len(values)} values"
    # sanity: at least SOME compression vs raw
    assert len(enc) < len(values) * 8

def test_gorilla_with_duplicates():
    # identical consecutive values take the cheapest path (zero XOR = 1 bit)
    values = [42.42] * 500
    enc = encode_gorilla(values)
    assert decode_gorilla(enc, len(values)) == values
    # 64 bits for first value + 1 bit per duplicate → ~64 bytes total
    assert len(enc) < 100


def test_gorilla_empty():
    assert encode_gorilla([]) == b""
    assert decode_gorilla(b"", 0) == []


def test_gorilla_nan_safe():
    # NaN has non-standard bit patterns; encode/decode must preserve them
    values = [float("nan"), 1.0, float("nan"), 2.0]
    dec = decode_gorilla(encode_gorilla(values), len(values))
    # NaN != NaN in Python, so compare bit patterns via struct
    import struct
    as_bits = lambda xs: [struct.pack("<d", x) for x in xs]
    assert as_bits(dec) == as_bits(values)

def test_gorilla_on_real_btcusdt():
    """Calibration: pin the encoder's behavior on real data.

    A future refactor that silently regresses Gorilla on real floats will
    fail this test. If you intentionally change the encoding, update the
    bounds — but know that you're changing the ratio.
    """
    from bench.datasets.load import load_binance_klines
    path = "bench/datasets/BTCUSDT-1m-2026-08.csv"
    import os
    if not os.path.exists(path):
        import pytest
        pytest.skip(f"{path} not present")
    rows = load_binance_klines(path, max_rows=5000)
    closes = [r["close"] for r in rows]
    enc = encode_gorilla(closes)
    per_value = len(enc) / len(closes)
    # empirically ~5.9 bytes/value on this data; assert a range
    assert 4.0 < per_value < 7.0, f"gorilla per-value {per_value:.2f} outside expected range"
