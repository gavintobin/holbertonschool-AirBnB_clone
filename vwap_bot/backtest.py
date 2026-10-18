"""Replay bars through the strategy, pricing options with Black-Scholes.

Option prices are modeled, not historical: a flat implied vol plus a
slippage haircut. Treat results as a sanity check on the logic, not as
expected returns. For realistic numbers, backtest against real option
quotes.
"""
from dataclasses import dataclass
from datetime import datetime

from .bars import Bar
from .config import Config
from .options import (Contract, black_scholes, contracts_for_budget,
                      pick_expiry, pick_strike, years_to_expiry)
from .strategy import ENTER, VWAPReversionStrategy


@dataclass
class Trade:
    contract: Contract
    qty: int
    entry_time: datetime
    entry_spot: float
    entry_premium: float
    entry_reason: str
    exit_time: datetime | None = None
    exit_spot: float | None = None
    exit_premium: float | None = None
    exit_reason: str | None = None
    commission: float = 0.0

    @property
    def pnl(self) -> float:
        if self.exit_premium is None:
            return 0.0
        gross = (self.exit_premium - self.entry_premium) * 100 * self.qty
        return gross - self.commission


def _premium(cfg: Config, c: Contract, spot: float, now: datetime) -> float:
    t = years_to_expiry(now, c.expiry)
    return black_scholes(spot, c.strike, t, cfg.risk_free_rate,
                         cfg.implied_vol, c.right)


def run_backtest(bars: list[Bar], cfg: Config) -> list[Trade]:
    strat = VWAPReversionStrategy(cfg)
    trades: list[Trade] = []
    open_trade: Trade | None = None

    for bar in bars:
        signal = strat.on_bar(bar)
        if signal is None:
            continue
        # Fill at the close of the signal bar
        now = bar.timestamp.replace(second=59)
        if signal.action == ENTER:
            contract = Contract(
                cfg.symbol,
                pick_expiry(bar.timestamp.date(), cfg.min_dte),
                signal.right,
                pick_strike(bar.close, signal.right, cfg.strike_increment,
                            cfg.otm_steps),
            )
            premium = _premium(cfg, contract, bar.close, now) * (1 + cfg.slippage_pct)
            qty = contracts_for_budget(premium, cfg.risk_per_trade, cfg.max_contracts)
            open_trade = Trade(contract, qty, bar.timestamp, bar.close, premium,
                               signal.reason,
                               commission=qty * cfg.commission_per_contract)
        elif open_trade is not None:
            premium = _premium(cfg, open_trade.contract, bar.close, now)
            open_trade.exit_premium = premium * (1 - cfg.slippage_pct)
            open_trade.exit_time = bar.timestamp
            open_trade.exit_spot = bar.close
            open_trade.exit_reason = signal.reason
            open_trade.commission += open_trade.qty * cfg.commission_per_contract
            trades.append(open_trade)
            open_trade = None

    return trades


def summarize(trades: list[Trade]) -> str:
    if not trades:
        return "No trades."
    lines = [f"{'entry':<17} {'exit':<6} {'contract':<22} {'qty':>3} "
             f"{'in':>7} {'out':>7} {'pnl':>9}  exit_reason"]
    for t in trades:
        lines.append(
            f"{t.entry_time:%Y-%m-%d %H:%M} {t.exit_time:%H:%M}  "
            f"{t.contract.symbol:<22} {t.qty:>3} {t.entry_premium:>7.2f} "
            f"{t.exit_premium:>7.2f} {t.pnl:>9.2f}  {t.exit_reason}")
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    by_reason = {}
    for t in trades:
        by_reason[t.exit_reason] = by_reason.get(t.exit_reason, 0) + 1
    lines += [
        "",
        f"trades: {len(trades)}   win rate: {len(wins) / len(trades):.1%}",
        f"total pnl: {sum(pnls):.2f}   avg win: "
        f"{(sum(wins) / len(wins)) if wins else 0:.2f}   avg loss: "
        f"{(sum(losses) / len(losses)) if losses else 0:.2f}",
        "exits: " + ", ".join(f"{k}={v}" for k, v in sorted(by_reason.items())),
    ]
    return "\n".join(lines)
