"""VWAP mean-reversion signal logic (broker independent)."""
from dataclasses import dataclass
from datetime import date

from .bars import Bar
from .config import Config
from .indicators import SessionVWAP

CALL, PUT = "call", "put"
ENTER, EXIT = "enter", "exit"


@dataclass
class Signal:
    action: str      # ENTER or EXIT
    right: str       # CALL or PUT
    reason: str      # lower_band / upper_band / vwap_target / stop / eod
    bar: Bar
    vwap: float
    sigma: float


class VWAPReversionStrategy:
    """Feed completed bars with on_bar(); act on the Signal it returns.

    - close <= VWAP - band_k*sigma  -> ENTER CALL
    - close >= VWAP + band_k*sigma  -> ENTER PUT
    - call exits when close >= VWAP, put exits when close <= VWAP
    - optional stop at VWAP -/+ stop_k*sigma, and a forced flatten near close

    A band must be re-armed (price closes back inside it while flat) before
    it can trigger again, so a stop-out does not instantly re-enter the same way.
    """

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.vwap = SessionVWAP()
        self.position: str | None = None
        self.session: date | None = None
        self.session_bars = 0
        self.call_armed = True
        self.put_armed = True

    def _new_session(self, day: date):
        self.session = day
        self.session_bars = 0
        self.call_armed = True
        self.put_armed = True

    def on_bar(self, bar: Bar) -> Signal | None:
        cfg = self.cfg
        t = bar.timestamp.time()
        if not (cfg.session_open <= t < cfg.session_close):
            return None  # regular-hours VWAP only

        if bar.timestamp.date() != self.session:
            self._new_session(bar.timestamp.date())
        self.session_bars += 1

        vwap, sigma = self.vwap.update(bar)
        if vwap is None:
            return None
        lower = vwap - cfg.band_k * sigma
        upper = vwap + cfg.band_k * sigma
        price = bar.close

        def sig(action, right, reason):
            return Signal(action, right, reason, bar, vwap, sigma)

        if self.position is not None:
            right = self.position
            if t >= cfg.flatten_time:
                reason = "eod"
            elif right == CALL and price >= vwap:
                reason = "vwap_target"
            elif right == PUT and price <= vwap:
                reason = "vwap_target"
            elif cfg.stop_k is not None and right == CALL and \
                    price <= vwap - cfg.stop_k * sigma:
                reason = "stop"
            elif cfg.stop_k is not None and right == PUT and \
                    price >= vwap + cfg.stop_k * sigma:
                reason = "stop"
            else:
                return None
            self.position = None
            return sig(EXIT, right, reason)

        # Re-arm only while flat, so a stop-out needs price to come back
        # inside the band before the same side can trigger again.
        if price > lower:
            self.call_armed = True
        if price < upper:
            self.put_armed = True

        if (self.session_bars <= cfg.warmup_bars or t >= cfg.entry_cutoff
                or sigma <= 0 or sigma < cfg.min_sigma):
            return None
        if price <= lower and self.call_armed:
            self.call_armed = False
            self.position = CALL
            return sig(ENTER, CALL, "lower_band")
        if price >= upper and self.put_armed:
            self.put_armed = False
            self.position = PUT
            return sig(ENTER, PUT, "upper_band")
        return None
