from mincore.pipeline import encode_ohlcv, decode_ohlcv
from bench.datasets.load import load_binance_klines


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
