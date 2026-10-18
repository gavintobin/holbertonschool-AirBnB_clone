"""CLI:  python -m vwap_bot {synth,backtest,run} ..."""
import argparse
import logging

from .backtest import run_backtest, summarize
from .bars import load_csv
from .config import Config


def main(argv=None):
    p = argparse.ArgumentParser(prog="vwap_bot")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("synth", help="write synthetic 1-min bars to a CSV")
    s.add_argument("out")
    s.add_argument("--days", type=int, default=5)
    s.add_argument("--seed", type=int, default=7)

    for name in ("backtest", "run"):
        c = sub.add_parser(name)
        if name == "backtest":
            c.add_argument("csv", help="timestamp,open,high,low,close,volume")
        else:
            c.add_argument("--live", action="store_true",
                           help="trade a LIVE account (default is paper)")
        c.add_argument("--symbol", default="SPY")
        c.add_argument("--band-k", type=float, default=1.0)
        c.add_argument("--stop-k", type=float, default=2.0,
                       help="stop distance in sigmas; 0 disables")
        c.add_argument("--min-dte", type=int, default=1)
        c.add_argument("--otm-steps", type=int, default=0)
        c.add_argument("--strike-increment", type=float, default=1.0)
        c.add_argument("--risk", type=float, default=500.0,
                       help="premium dollars per trade")
        c.add_argument("--iv", type=float, default=0.18,
                       help="backtest implied vol assumption")

    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    if a.cmd == "synth":
        from .synth import write_csv
        n = write_csv(a.out, days=a.days, seed=a.seed)
        print(f"wrote {n} bars to {a.out}")
        return

    cfg = Config(symbol=a.symbol, band_k=a.band_k,
                 stop_k=a.stop_k or None, min_dte=a.min_dte,
                 otm_steps=a.otm_steps, strike_increment=a.strike_increment,
                 risk_per_trade=a.risk, implied_vol=a.iv)

    if a.cmd == "backtest":
        print(summarize(run_backtest(load_csv(a.csv), cfg)))
    else:
        from .alpaca_runner import AlpacaRunner
        AlpacaRunner(cfg, paper=not a.live).run()


if __name__ == "__main__":
    main()
