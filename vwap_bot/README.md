# VWAP Mean-Reversion Options Bot

Trades the bet that price snaps back to intraday VWAP after it stretches one
standard deviation away from it.

| Condition (on a closed 1-min bar)    | Action    |
|--------------------------------------|-----------|
| close <= VWAP − 1σ                   | buy call  |
| close >= VWAP + 1σ                   | buy put   |
| call open and close >= VWAP          | sell call |
| put open and close <= VWAP           | sell put  |

**VWAP** is anchored to the regular session (09:30–16:00 ET) and resets every
day. **σ** is the volume-weighted standard deviation of typical price
`(H+L+C)/3` around VWAP, which is the standard "VWAP bands" definition.

### Guardrails (all configurable in `config.py`)
- **Warm-up:** no entries in the first 15 bars, because σ is close to zero
  at the open and the bands would trigger on noise.
- **Stop:** exit if price runs to VWAP ∓ 2σ (`--stop-k 0` turns this off).
  Mean reversion loses on trend days, and this is the main protection.
- **Re-arm:** after a trade, a band can't fire again until price closes back
  inside it, so a stop-out doesn't re-enter the same losing trade on the
  next bar.
- **Time:** no new entries after 15:30, and everything is closed at 15:55.
- **One position at a time.** Size is `risk_per_trade` dollars of premium,
  capped at `max_contracts`.
- **Contract:** at-the-money (`--otm-steps N` to go further out of the
  money), nearest expiry at least `--min-dte` days out (default 1; 0 = 0DTE).

## Usage

```bash
# Backtest (no dependencies beyond the standard library)
python -m vwap_bot synth spy.csv --days 5     # synthetic demo data
python -m vwap_bot backtest spy.csv           # or your own CSV
#   CSV columns: timestamp,open,high,low,close,volume  (naive times = ET)

# Paper trade on Alpaca
pip install -r vwap_bot/requirements.txt
export ALPACA_API_KEY=... ALPACA_SECRET_KEY=...
python -m vwap_bot run --symbol SPY           # paper account
python -m vwap_bot run --symbol SPY --live    # real money: opt-in only

# Tests
python -m unittest discover -s vwap_bot/tests -t .
```

Start the runner before 09:30 ET. It replays the session's bars, so starting
late still gives the correct VWAP, and it closes any open position at the
session close.

## Caveats, read before trading real money
- **Backtest option prices are modeled** with Black-Scholes, a flat IV and
  slippage. They aren't real quotes, so vol crush, wide spreads and skew
  aren't captured. The synthetic data is mean-reverting by construction, so
  its results tell you the logic works, not that the strategy makes money.
  Backtest on real minute bars and option quotes first.
- Options are a lossy proxy for a reversion of a few tenths of a point:
  theta and the bid/ask spread can eat most of it. Look at average
  winner vs. loser after costs, not just win rate.
- The live runner uses market orders and keeps position state in memory. If
  you restart it mid-trade, check the account for an open position yourself.
- This isn't financial advice. Paper trade it for a while first.
