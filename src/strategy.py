"""Definicion UNICA de estrategias, compartida por el bot en vivo y el backtest.

Una estrategia implementa `compute(df)`: recibe un DataFrame OHLCV
(columnas open/high/low/close/volume) y devuelve el mismo DataFrame con:
  - las columnas de indicadores que use (para poder graficarlas), y
  - dos columnas booleanas: `entry` (abrir posicion) y `exit` (cerrar posicion).

- El bot en vivo llama `strategy.signal(df)` -> Signal.BUY / SELL / HOLD
  (mira solo la ultima fila, que debe ser una vela ya cerrada).
- El backtest precalcula `entry`/`exit` una sola vez y los recorre vela a vela.

Para agregar una estrategia nueva: subclase de `Strategy`, definis `key`,
`defaults` y `compute`, y la sumas a `STRATEGIES`.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

import pandas as pd

from src.indicators import rsi, sma


class Signal(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Strategy(ABC):
    key: str = ""
    defaults: dict = {}

    def __init__(self, **overrides) -> None:
        desconocidos = set(overrides) - set(self.defaults)
        if desconocidos:
            raise ValueError(
                f"Parametros no validos para {self.key}: {sorted(desconocidos)}. "
                f"Validos: {sorted(self.defaults)}"
            )
        self.p = {**self.defaults, **overrides}

    @abstractmethod
    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        """Agrega indicadores + columnas booleanas `entry` y `exit`."""

    def signal(self, df: pd.DataFrame) -> Signal:
        """Senal para la ultima vela del DataFrame (debe estar cerrada)."""
        data = self.compute(df)
        if len(data) < 2:
            return Signal.HOLD
        last = data.iloc[-1]
        if bool(last["entry"]):
            return Signal.BUY
        if bool(last["exit"]):
            return Signal.SELL
        return Signal.HOLD

    @staticmethod
    def _clean_flags(df: pd.DataFrame) -> pd.DataFrame:
        df[["entry", "exit"]] = df[["entry", "exit"]].fillna(False).astype(bool)
        return df


class SmaCrossRsi(Strategy):
    """Cruce de medias moviles con filtro de RSI (la estrategia original)."""

    key = "sma_cross_rsi"
    defaults = dict(fast_ma=20, slow_ma=50, rsi_period=14, rsi_min=45.0, rsi_max=70.0)

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        p = self.p
        d["fast"] = sma(d["close"], p["fast_ma"])
        d["slow"] = sma(d["close"], p["slow_ma"])
        d["rsi"] = rsi(d["close"], p["rsi_period"])

        cruce_alcista = (d["fast"].shift(1) <= d["slow"].shift(1)) & (d["fast"] > d["slow"])
        cruce_bajista = (d["fast"].shift(1) >= d["slow"].shift(1)) & (d["fast"] < d["slow"])

        d["entry"] = cruce_alcista & d["rsi"].between(p["rsi_min"], p["rsi_max"])
        d["exit"] = cruce_bajista
        return self._clean_flags(d)


class RsiReversion(Strategy):
    """Reversion a la media: compra sobrevendido, vende cuando el RSI recupera."""

    key = "rsi_reversion"
    defaults = dict(rsi_period=14, rsi_buy=30.0, rsi_exit=55.0)

    def compute(self, df: pd.DataFrame) -> pd.DataFrame:
        d = df.copy()
        p = self.p
        d["rsi"] = rsi(d["close"], p["rsi_period"])
        d["entry"] = d["rsi"] < p["rsi_buy"]
        d["exit"] = d["rsi"] > p["rsi_exit"]
        return self._clean_flags(d)


STRATEGIES: dict[str, type[Strategy]] = {
    cls.key: cls for cls in (SmaCrossRsi, RsiReversion)
}


def build_strategy(key: str, **overrides) -> Strategy:
    try:
        cls = STRATEGIES[key]
    except KeyError:
        raise ValueError(
            f"Estrategia desconocida: {key!r}. Opciones: {', '.join(STRATEGIES)}"
        ) from None
    return cls(**overrides)


def strategy_from_settings(settings, key: str | None = None, **extra) -> Strategy:
    """Construye la estrategia leyendo de `settings` solo los parametros que use.

    `key` sobreescribe settings.strategy; `extra` sobreescribe cualquier parametro.
    """
    key = key or settings.strategy
    cls = STRATEGIES.get(key)
    if cls is None:
        raise ValueError(
            f"Estrategia desconocida: {key!r}. Opciones: {', '.join(STRATEGIES)}"
        )
    overrides = {k: getattr(settings, k) for k in cls.defaults if hasattr(settings, k)}
    overrides.update(extra)
    return cls(**overrides)
