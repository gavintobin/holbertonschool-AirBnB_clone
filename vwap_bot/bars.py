"""Bar type and CSV loading."""
import csv
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class Bar:
    timestamp: datetime  # bar open time, tz-aware US/Eastern
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def typical_price(self) -> float:
        return (self.high + self.low + self.close) / 3.0


def to_et(ts: datetime) -> datetime:
    """Treat naive timestamps as Eastern; convert aware ones to Eastern."""
    if ts.tzinfo is None:
        return ts.replace(tzinfo=ET)
    return ts.astimezone(ET)


def load_csv(path: str) -> list[Bar]:
    """Load bars from a CSV with columns timestamp,open,high,low,close,volume."""
    bars = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            row = {k.strip().lower(): v for k, v in row.items()}
            bars.append(Bar(
                timestamp=to_et(datetime.fromisoformat(row["timestamp"])),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            ))
    bars.sort(key=lambda b: b.timestamp)
    return bars
