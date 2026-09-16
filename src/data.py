"""Descarga de datos OHLCV y conversion a DataFrame de pandas."""
from __future__ import annotations

import pandas as pd
from binance.client import Client

_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_base", "taker_quote", "ignore",
]


def klines_to_df(raw: list) -> pd.DataFrame:
    """Convierte la respuesta cruda de klines de Binance en un DataFrame indexado por tiempo."""
    df = pd.DataFrame(raw, columns=_COLUMNS)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df = df.set_index("open_time")
    return df[["open", "high", "low", "close", "volume"]]


def load_history(
    client: Client, symbol: str, interval: str, start: str, end: str | None = None
) -> pd.DataFrame:
    """Descarga historico entre `start` y `end` (ej. '1 Jan 2023'). `end` vacio = hasta hoy."""
    raw = client.get_historical_klines(symbol, interval, start, end)
    return klines_to_df(raw)
