"""Option contract helpers: strike/expiry selection, OCC symbols, pricing."""
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time

from .bars import ET
from .strategy import CALL


@dataclass(frozen=True)
class Contract:
    underlying: str
    expiry: date
    right: str
    strike: float

    @property
    def symbol(self) -> str:
        return occ_symbol(self.underlying, self.expiry, self.right, self.strike)


def occ_symbol(underlying: str, expiry: date, right: str, strike: float) -> str:
    """e.g. SPY 2026-10-19 call 580 -> SPY261019C00580000"""
    cp = "C" if right == CALL else "P"
    return f"{underlying.upper()}{expiry:%y%m%d}{cp}{round(strike * 1000):08d}"


def pick_strike(price: float, right: str, increment: float, otm_steps: int = 0) -> float:
    atm = round(price / increment) * increment
    step = increment * otm_steps
    return atm + step if right == CALL else atm - step


def pick_expiry(today: date, min_dte: int) -> date:
    """First weekday at least min_dte calendar days out (holidays ignored)."""
    d = today + timedelta(days=min_dte)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def years_to_expiry(now: datetime, expiry: date) -> float:
    exp = datetime.combine(expiry, time(16, 0), tzinfo=ET)
    seconds = max((exp - now).total_seconds(), 60.0)  # floor at one minute
    return seconds / (365.0 * 24 * 3600)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def black_scholes(spot: float, strike: float, t: float, r: float,
                  sigma: float, right: str) -> float:
    if t <= 0 or sigma <= 0:
        intrinsic = spot - strike if right == CALL else strike - spot
        return max(intrinsic, 0.0)
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (r + 0.5 * sigma ** 2) * t) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if right == CALL:
        return spot * _norm_cdf(d1) - strike * math.exp(-r * t) * _norm_cdf(d2)
    return strike * math.exp(-r * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


def contracts_for_budget(premium: float, budget: float, max_contracts: int) -> int:
    if premium <= 0:
        return 0
    return max(1, min(max_contracts, int(budget // (premium * 100))))
