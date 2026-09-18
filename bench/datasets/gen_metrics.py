import random, csv
random.seed(7)
with open("bench/datasets/metrics_synthetic.csv", "w", newline="") as f:
    w = csv.writer(f)
    for i in range(10_000):
        w.writerow([
            i * 1000,                          # timestamp
            random.randint(0, 100),            # cpu_pct (small int, lots of repeats)
            random.randint(0, 65535),          # mem_kb
            random.choice(["ok", "warn", "err"]),  # status
            round(random.gauss(50, 5), 3),     # latency_ms
        ])
