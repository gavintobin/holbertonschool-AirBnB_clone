"""Generate synthetic 1-minute bars (mean-reverting random walk) for demos."""
import csv
import math
import random
from datetime import date, datetime, time, timedelta

from .bars import ET


def generate(days: int = 5, start: date = date(2026, 10, 12), price: float = 580.0,
             seed: int = 7) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    d = start
    made = 0
    while made < days:
        if d.weekday() < 5:
            anchor = price
            ts = datetime.combine(d, time(9, 30), tzinfo=ET)
            for i in range(390):
                # Ornstein-Uhlenbeck pull toward a slowly drifting anchor
                anchor += rng.gauss(0, 0.05)
                price += 0.04 * (anchor - price) + rng.gauss(0, 0.25)
                o = price - rng.gauss(0, 0.05)
                hi = max(o, price) + abs(rng.gauss(0, 0.08))
                lo = min(o, price) - abs(rng.gauss(0, 0.08))
                u = 1.0 + 1.5 * math.cos(math.pi * i / 389) ** 2  # U-shaped volume
                vol = int(rng.uniform(0.6, 1.4) * 50_000 * u)
                rows.append({"timestamp": ts.isoformat(), "open": round(o, 2),
                             "high": round(hi, 2), "low": round(lo, 2),
                             "close": round(price, 2), "volume": vol})
                ts += timedelta(minutes=1)
            made += 1
        d += timedelta(days=1)
    return rows


def write_csv(path: str, **kwargs):
    rows = generate(**kwargs)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return len(rows)
