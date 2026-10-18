"""VWAP mean-reversion options bot.

Buy calls when price closes at/below VWAP - k*sigma, buy puts when price
closes at/above VWAP + k*sigma, and exit when price returns to VWAP.
"""
from .config import Config
from .bars import Bar, load_csv
from .indicators import SessionVWAP
from .strategy import Signal, VWAPReversionStrategy

__all__ = ["Config", "Bar", "load_csv", "SessionVWAP", "Signal",
           "VWAPReversionStrategy"]
