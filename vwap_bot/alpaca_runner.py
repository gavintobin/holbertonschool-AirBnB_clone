"""Run the strategy against Alpaca (paper by default).

Requires `pip install alpaca-py` and the env vars ALPACA_API_KEY and
ALPACA_SECRET_KEY. The account needs options trading enabled.
"""
import logging
import os
import time as _time
from datetime import datetime, timedelta

from .bars import ET, Bar
from .config import Config
from .options import contracts_for_budget, pick_expiry, pick_strike
from .strategy import CALL, ENTER, VWAPReversionStrategy

log = logging.getLogger("vwap_bot")


class AlpacaRunner:
    def __init__(self, cfg: Config, paper: bool = True, feed: str = "iex"):
        from alpaca.data.enums import DataFeed
        from alpaca.data.historical import (OptionHistoricalDataClient,
                                            StockHistoricalDataClient)
        from alpaca.trading.client import TradingClient

        key = os.environ["ALPACA_API_KEY"]
        secret = os.environ["ALPACA_SECRET_KEY"]
        self.cfg = cfg
        self.trading = TradingClient(key, secret, paper=paper)
        self.stock_data = StockHistoricalDataClient(key, secret)
        self.option_data = OptionHistoricalDataClient(key, secret)
        self.feed = DataFeed(feed)
        self.strategy = VWAPReversionStrategy(cfg)
        self.last_bar_ts: datetime | None = None
        self.open_symbol: str | None = None

    # ---- market data -------------------------------------------------
    def _session_bars(self, now: datetime) -> list[Bar]:
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        start = datetime.combine(now.date(), self.cfg.session_open, tzinfo=ET)
        req = StockBarsRequest(symbol_or_symbols=self.cfg.symbol,
                               timeframe=TimeFrame.Minute, start=start,
                               feed=self.feed)
        raw = self.stock_data.get_stock_bars(req).data.get(self.cfg.symbol, [])
        bars = [Bar(b.timestamp.astimezone(ET), b.open, b.high, b.low, b.close,
                    b.volume) for b in raw]
        # only bars that have fully closed
        return [b for b in bars if b.timestamp + timedelta(minutes=1) <= now]

    # ---- orders ------------------------------------------------------
    def _find_contract(self, right: str, spot: float, today):
        from alpaca.trading.enums import ContractType
        from alpaca.trading.requests import GetOptionContractsRequest

        cfg = self.cfg
        target = pick_strike(spot, right, cfg.strike_increment, cfg.otm_steps)
        earliest = pick_expiry(today, cfg.min_dte)
        req = GetOptionContractsRequest(
            underlying_symbols=[cfg.symbol],
            type=ContractType.CALL if right == CALL else ContractType.PUT,
            expiration_date_gte=earliest,
            expiration_date_lte=earliest + timedelta(days=7),
            strike_price_gte=str(target - 5 * cfg.strike_increment),
            strike_price_lte=str(target + 5 * cfg.strike_increment),
            limit=500,
        )
        contracts = self.trading.get_option_contracts(req).option_contracts or []
        if not contracts:
            return None
        nearest_exp = min(c.expiration_date for c in contracts)
        same_exp = [c for c in contracts if c.expiration_date == nearest_exp]
        return min(same_exp, key=lambda c: abs(float(c.strike_price) - target))

    def _ask(self, symbol: str) -> float | None:
        from alpaca.data.requests import OptionLatestQuoteRequest

        q = self.option_data.get_option_latest_quote(
            OptionLatestQuoteRequest(symbol_or_symbols=symbol)).get(symbol)
        return float(q.ask_price) if q and q.ask_price else None

    def _enter(self, right: str, spot: float, today):
        from alpaca.trading.enums import OrderSide, TimeInForce
        from alpaca.trading.requests import MarketOrderRequest

        contract = self._find_contract(right, spot, today)
        if contract is None:
            log.warning("no %s contract found near %.2f", right, spot)
            return
        ask = self._ask(contract.symbol)
        if not ask:
            log.warning("no quote for %s, skipping entry", contract.symbol)
            return
        qty = contracts_for_budget(ask, self.cfg.risk_per_trade,
                                   self.cfg.max_contracts)
        self.trading.submit_order(MarketOrderRequest(
            symbol=contract.symbol, qty=qty, side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY))
        self.open_symbol = contract.symbol
        log.info("BUY %d %s @ ~%.2f", qty, contract.symbol, ask)

    def _exit(self, reason: str):
        if self.open_symbol is None:
            return
        self.trading.close_position(self.open_symbol)
        log.info("CLOSE %s (%s)", self.open_symbol, reason)
        self.open_symbol = None

    # ---- loop --------------------------------------------------------
    def step(self, now: datetime):
        for bar in self._session_bars(now):
            if self.last_bar_ts is not None and bar.timestamp <= self.last_bar_ts:
                continue
            self.last_bar_ts = bar.timestamp
            signal = self.strategy.on_bar(bar)
            if signal is None:
                continue
            log.info("%s %s %s close=%.2f vwap=%.2f sigma=%.3f",
                     bar.timestamp.strftime("%H:%M"), signal.action,
                     signal.right, bar.close, signal.vwap, signal.sigma)
            if signal.action == ENTER:
                self._enter(signal.right, bar.close, bar.timestamp.date())
            else:
                self._exit(signal.reason)

    def run(self):
        log.info("starting VWAP reversion bot on %s", self.cfg.symbol)
        while True:
            now = datetime.now(ET)
            if now.time() >= self.cfg.session_close:
                self._exit("session_close")
                log.info("session over")
                return
            if now.time() >= self.cfg.session_open:
                try:
                    self.step(now)
                except Exception:
                    log.exception("step failed; will retry next minute")
            # wake a few seconds after each minute so the bar has closed
            nxt = (now + timedelta(minutes=1)).replace(second=3, microsecond=0)
            _time.sleep(max((nxt - datetime.now(ET)).total_seconds(), 1))
