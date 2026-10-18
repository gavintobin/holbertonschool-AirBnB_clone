"""Strategy and execution settings."""
from dataclasses import dataclass
from datetime import time


@dataclass
class Config:
    symbol: str = "SPY"

    # Bands: entries at VWAP +/- band_k * sigma
    band_k: float = 1.0
    # Stop out if price keeps running to VWAP +/- stop_k * sigma (None = off)
    stop_k: float | None = 2.0

    # Session timing (US/Eastern)
    session_open: time = time(9, 30)
    session_close: time = time(16, 0)
    warmup_bars: int = 15            # sigma is meaningless in the first minutes
    entry_cutoff: time = time(15, 30)  # no new entries after this
    flatten_time: time = time(15, 55)  # force-exit anything still open

    # Ignore signals while the bands are too tight to be worth trading
    min_sigma: float = 0.0

    # Option selection
    min_dte: int = 1                 # 0 = same-day expiry
    strike_increment: float = 1.0
    otm_steps: int = 0               # 0 = ATM, 1 = one strike out of the money

    # Sizing
    risk_per_trade: float = 500.0    # dollars of premium per entry
    max_contracts: int = 10

    # Backtest pricing assumptions (Black-Scholes)
    implied_vol: float = 0.18
    risk_free_rate: float = 0.04
    slippage_pct: float = 0.02       # paid on each side of the option fill
    commission_per_contract: float = 0.65
