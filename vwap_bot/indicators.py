"""Session-anchored VWAP with volume-weighted standard deviation bands."""
import math
from datetime import date

from .bars import Bar


class SessionVWAP:
    """Incremental VWAP that resets at the start of every trading day.

    sigma is the volume-weighted standard deviation of typical price
    around VWAP:  sqrt( sum(v * p^2) / sum(v) - vwap^2 ).
    """

    def __init__(self):
        self.reset()

    def reset(self, session: date | None = None):
        self.session = session
        self.cum_v = 0.0
        self.cum_pv = 0.0
        self.cum_p2v = 0.0
        self.vwap = None
        self.sigma = None

    def update(self, bar: Bar):
        """Add a bar; return (vwap, sigma) or (None, None) if no volume yet."""
        day = bar.timestamp.date()
        if day != self.session:
            self.reset(day)
        if bar.volume > 0:
            p = bar.typical_price
            self.cum_v += bar.volume
            self.cum_pv += p * bar.volume
            self.cum_p2v += p * p * bar.volume
        if self.cum_v == 0:
            return None, None
        self.vwap = self.cum_pv / self.cum_v
        var = self.cum_p2v / self.cum_v - self.vwap ** 2
        self.sigma = math.sqrt(max(var, 0.0))
        return self.vwap, self.sigma
