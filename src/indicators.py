"""Indicadores tecnicos basicos, implementados con pandas (sin dependencias extra)."""
from __future__ import annotations

import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    """RSI de Wilder (media exponencial con alpha = 1/length)."""
    delta = series.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
