import unittest
from datetime import date, datetime, time, timedelta

from vwap_bot.backtest import run_backtest
from vwap_bot.bars import ET, Bar
from vwap_bot.config import Config
from vwap_bot.indicators import SessionVWAP
from vwap_bot.options import (black_scholes, contracts_for_budget, occ_symbol,
                              pick_expiry, pick_strike)
from vwap_bot.strategy import CALL, ENTER, EXIT, PUT, VWAPReversionStrategy
from vwap_bot.synth import generate

DAY = date(2026, 10, 13)


def bar(minute, price, volume=1000, day=DAY):
    ts = datetime.combine(day, time(9, 30), tzinfo=ET) + timedelta(minutes=minute)
    return Bar(ts, price, price, price, price, volume)


def feed(strategy, prices, start=0):
    return [strategy.on_bar(bar(start + i, p)) for i, p in enumerate(prices)]


class TestSessionVWAP(unittest.TestCase):
    def test_vwap_and_sigma(self):
        v = SessionVWAP()
        v.update(bar(0, 10, volume=1))
        vwap, sigma = v.update(bar(1, 20, volume=3))
        self.assertAlmostEqual(vwap, 17.5)
        # E[p^2] = (100 + 1200) / 4 = 325 ; var = 325 - 306.25
        self.assertAlmostEqual(sigma, 18.75 ** 0.5)

    def test_resets_each_day(self):
        v = SessionVWAP()
        v.update(bar(0, 100))
        vwap, sigma = v.update(bar(0, 50, day=DAY + timedelta(days=1)))
        self.assertEqual((vwap, sigma), (50, 0))

    def test_zero_volume(self):
        self.assertEqual(SessionVWAP().update(bar(0, 10, volume=0)), (None, None))


class TestStrategy(unittest.TestCase):
    def setUp(self):
        self.cfg = Config(warmup_bars=4, stop_k=None)
        self.s = VWAPReversionStrategy(self.cfg)
        # Oscillate to build a sigma of roughly 1 around 100
        feed(self.s, [99, 101, 99, 101])

    def test_buy_call_below_band_then_exit_at_vwap(self):
        sig = self.s.on_bar(bar(4, 98))
        self.assertEqual((sig.action, sig.right), (ENTER, CALL))
        self.assertLessEqual(98, sig.vwap - sig.sigma)
        self.assertIsNone(self.s.on_bar(bar(5, 99)))  # still below vwap
        sig = self.s.on_bar(bar(6, 100.5))
        self.assertEqual((sig.action, sig.right, sig.reason),
                         (EXIT, CALL, "vwap_target"))

    def test_buy_put_above_band_then_exit_at_vwap(self):
        sig = self.s.on_bar(bar(4, 102))
        self.assertEqual((sig.action, sig.right), (ENTER, PUT))
        sig = self.s.on_bar(bar(5, 99.5))
        self.assertEqual((sig.action, sig.right, sig.reason),
                         (EXIT, PUT, "vwap_target"))

    def test_no_signal_inside_bands(self):
        self.assertIsNone(self.s.on_bar(bar(4, 100.2)))

    def test_no_entry_during_warmup(self):
        s = VWAPReversionStrategy(Config(warmup_bars=10))
        self.assertTrue(all(x is None for x in feed(s, [99, 101, 99, 101, 95])))

    def test_eod_flatten_and_entry_cutoff(self):
        self.s.on_bar(bar(4, 98))
        sig = self.s.on_bar(bar(385, 97))  # 15:55
        self.assertEqual((sig.action, sig.reason), (EXIT, "eod"))
        self.assertIsNone(self.s.on_bar(bar(386, 90)))  # past entry cutoff

    def test_stop_then_requires_rearm(self):
        s = VWAPReversionStrategy(Config(warmup_bars=4, stop_k=2.0))
        feed(s, [99, 101, 99, 101])
        self.assertEqual(s.on_bar(bar(4, 98)).action, ENTER)
        sig = s.on_bar(bar(5, 90))
        self.assertEqual((sig.action, sig.reason), (EXIT, "stop"))
        # still beyond the lower band: must not re-enter immediately
        self.assertIsNone(s.on_bar(bar(6, 90)))

    def test_ignores_premarket(self):
        pre = Bar(datetime(2026, 10, 13, 8, 0, tzinfo=ET), 1, 1, 1, 1, 10 ** 9)
        self.assertIsNone(self.s.on_bar(pre))
        self.assertAlmostEqual(self.s.vwap.vwap, 100)


class TestOptions(unittest.TestCase):
    def test_occ_symbol(self):
        self.assertEqual(occ_symbol("spy", date(2026, 10, 19), CALL, 580),
                         "SPY261019C00580000")
        self.assertEqual(occ_symbol("SPY", date(2026, 10, 19), PUT, 580.5),
                         "SPY261019P00580500")

    def test_strike_selection(self):
        self.assertEqual(pick_strike(580.4, CALL, 1), 580)
        self.assertEqual(pick_strike(580.4, CALL, 1, otm_steps=2), 582)
        self.assertEqual(pick_strike(580.4, PUT, 1, otm_steps=2), 578)
        self.assertEqual(pick_strike(583, PUT, 5), 585)

    def test_expiry_skips_weekend(self):
        friday = date(2026, 10, 16)
        self.assertEqual(pick_expiry(friday, 0), friday)
        self.assertEqual(pick_expiry(friday, 1), date(2026, 10, 19))

    def test_black_scholes_put_call_parity(self):
        s, k, t, r, v = 100, 100, 0.1, 0.04, 0.2
        c = black_scholes(s, k, t, r, v, CALL)
        p = black_scholes(s, k, t, r, v, PUT)
        self.assertAlmostEqual(c - p, s - k * 2.718281828459045 ** (-r * t), 6)

    def test_sizing(self):
        self.assertEqual(contracts_for_budget(2.4, 500, 10), 2)
        self.assertEqual(contracts_for_budget(9.0, 500, 10), 1)  # min 1
        self.assertEqual(contracts_for_budget(0.1, 500, 10), 10)  # capped


class TestBacktest(unittest.TestCase):
    def test_runs_and_closes_every_trade(self):
        rows = generate(days=3)
        bars = [Bar(datetime.fromisoformat(r["timestamp"]), r["open"], r["high"],
                    r["low"], r["close"], r["volume"]) for r in rows]
        trades = run_backtest(bars, Config())
        self.assertTrue(trades)
        for t in trades:
            self.assertIsNotNone(t.exit_time)
            self.assertEqual(t.entry_time.date(), t.exit_time.date())
            if t.exit_reason == "vwap_target":
                above = t.exit_spot >= t.entry_spot
                self.assertEqual(above, t.contract.right == CALL)


if __name__ == "__main__":
    unittest.main()
