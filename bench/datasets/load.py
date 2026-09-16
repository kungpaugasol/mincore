import csv

def load_binance_klines(path, max_rows=None):
    """
    Returns a list of dicts with keys:
        timestamp, open, high, low, close, volume
    """
    rows = []
    with open(path, "r", newline="") as f:
        reader = csv.reader(f)
        for i, raw in enumerate(reader):
            if max_rows is not None and i >= max_rows:
                break
            # Binance has no header; columns are positional
            rows.append({
                "timestamp": int(raw[0]),   # ms
                "open":      float(raw[1]),
                "high":      float(raw[2]),
                "low":       float(raw[3]),
                "close":     float(raw[4]),
                "volume":    float(raw[5]),
            })
    return rows
