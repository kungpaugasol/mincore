from mincore.pipeline import encode_ohlcv, decode_ohlcv
from bench.datasets.load import load_binance_klines
from mincore.select import select_encoder

def test_pipeline_roundtrip_small():
    rows = load_binance_klines(
        "bench/datasets/BTCUSDT-1m-2026-08.csv", max_rows=100,
    )
    data = encode_ohlcv(rows)
    n, decoded = decode_ohlcv(data)
    assert n == 100
    assert decoded["timestamp"] == [r["timestamp"] for r in rows]
    assert decoded["open"] == [r["open"] for r in rows]
    assert decoded["close"] == [r["close"] for r in rows]


def test_pipeline_roundtrip_full_month():
    rows = load_binance_klines("bench/datasets/BTCUSDT-1m-2026-08.csv")
    data = encode_ohlcv(rows)
    n, decoded = decode_ohlcv(data)
    assert n == len(rows)
    assert decoded["close"] == [r["close"] for r in rows]


def test_pipeline_with_symbols():
    btc = load_binance_klines("bench/datasets/BTCUSDT-1m-2026-08.csv", max_rows=50)
    eth = load_binance_klines("bench/datasets/ETHUSDT-1m-2026-08.csv", max_rows=50)
    rows = btc + eth
    symbols = ["BTCUSDT"] * 50 + ["ETHUSDT"] * 50
    data = encode_ohlcv(rows, symbols=symbols)
    n, decoded = decode_ohlcv(data)
    assert n == 100
    assert decoded["symbol"] == symbols

def test_selector_matches_manual_choices():
    """The selector should reproduce the per column encoders we picked by hand
    in Phase 1. If it doesn't, either selection is broken or applicability
    checks are wrong."""
    rows = load_binance_klines("bench/datasets/BTCUSDT-1m-2026-08.csv", max_rows=5000)

    ts = [r["timestamp"] for r in rows]
    assert select_encoder(ts) == "dod", f"timestamp picked {select_encoder(ts)}"

    for name in ("open", "high", "low", "close"):
        vals = [r[name] for r in rows]
        assert select_encoder(vals) == "gorilla", f"{name} picked {select_encoder(vals)}"

    vol_int = [int(round(r["volume"] * 1e8)) for r in rows]
    assert select_encoder(vol_int) == "dod", f"volume picked {select_encoder(vol_int)}"


def test_selector_handles_strings():
    symbols = ["BTCUSDT"] * 100 + ["ETHUSDT"] * 100
    assert select_encoder(symbols) == "dict"


def test_selector_falls_back_on_garbage():
    # a mixed list that no encoder claims cleanly
    from mincore.select import select_encoder as se
    # this shouldn't raise; it should pick something or fall back to varint
    result = se([1, 2, 3, 4, 5])
    assert result in ("dod", "varint")   # both plausible on small int lists


def test_selector_empty():
    from mincore.select import select_encoder as se
    assert se([]) == "varint"

def test_selector_on_non_financial_data():
    import csv
    from mincore.select import select_encoder
    # small synthetic set: ints with repeats, strings, floats
    ints_small_range = [random.randint(0, 100) for _ in range(2000)]
    ints_wide_range  = [random.randint(0, 1 << 30) for _ in range(2000)]
    strings_low_card = [random.choice(["ok", "warn", "err"]) for _ in range(2000)]
    floats_smooth    = [100.0 + i * 0.01 for i in range(2000)]

    assert select_encoder(ints_small_range) in ("dod", "varint")
    assert select_encoder(ints_wide_range) in ("dod", "varint")
    assert select_encoder(strings_low_card) == "dict"
    assert select_encoder(floats_smooth) == "gorilla"
