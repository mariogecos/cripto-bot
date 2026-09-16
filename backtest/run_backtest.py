"""Backtest de cualquier estrategia definida en src/strategy.py.

Usa la MISMA definicion de estrategia que el bot en vivo (metodo `compute`).

Ejemplos:
    python -m backtest.run_backtest --symbol BTCUSDT --interval 1h --start "1 Jan 2024"
    python -m backtest.run_backtest --strategy rsi_reversion --interval 4h
    python -m backtest.run_backtest --strategy sma_cross_rsi --params "fast_ma=50,slow_ma=200"

Descarga datos publicos de Binance (no requiere API key).
"""
from __future__ import annotations

import argparse

from backtesting import Strategy as BtStrategy
from backtesting.lib import FractionalBacktest
from binance.client import Client

from config import settings
from src.data import load_history
from src.strategy import STRATEGIES, Strategy, strategy_from_settings


def _make_adapter(strat: Strategy, sl_pct: float, tp_pct: float) -> type[BtStrategy]:
    """Envuelve una estrategia nuestra en una clase que backtesting.py entiende."""

    class _Adapter(BtStrategy):
        def init(self) -> None:
            ohlcv = self.data.df.rename(columns=str.lower)
            comp = strat.compute(ohlcv)
            # Registramos como "indicadores" para que backtesting los alinee por vela.
            self._entry = self.I(lambda: comp["entry"].to_numpy(float), name="entry", plot=False)
            self._exit = self.I(lambda: comp["exit"].to_numpy(float), name="exit", plot=False)
            for col in comp.columns:
                if col not in ("open", "high", "low", "close", "volume", "entry", "exit"):
                    self.I(lambda c=col: comp[c].to_numpy(float), name=col)

        def next(self) -> None:
            price = self.data.Close[-1]
            if not self.position and self._entry[-1]:
                self.buy(size=.95, sl=price * (1 - sl_pct), tp=price * (1 + tp_pct))
            elif self.position and self._exit[-1]:
                self.position.close()

    return _Adapter


def _parse_params(text: str) -> dict:
    out: dict = {}
    for pair in filter(None, (s.strip() for s in text.split(","))):
        k, _, v = pair.partition("=")
        try:
            out[k.strip()] = int(v)
        except ValueError:
            out[k.strip()] = float(v)
    return out


def run_backtest(
    strategy_key: str,
    symbol: str,
    interval: str,
    start: str,
    end: str | None = None,
    cash: float = 10_000,
    sl: float = settings.stop_loss_pct,
    tp: float = settings.take_profit_pct,
    strategy_params: dict | None = None,
    report_path: str = "backtest/report.html",
    plot: bool = True,
):
    """Corre un backtest y devuelve las stats de backtesting.py. Imprime resultado (y grafico)."""
    strat = strategy_from_settings(settings, key=strategy_key, **(strategy_params or {}))
    print(f"Estrategia: {strat.key} | parametros: {strat.p}")

    client = Client()  # sin testnet: necesitamos historico largo
    df = load_history(client, symbol, interval, start, end)
    df = df.rename(
        columns={"open": "Open", "high": "High", "low": "Low",
                 "close": "Close", "volume": "Volume"}
    )
    if df.empty:
        raise ValueError("No se descargaron velas para ese rango de fechas/simbolo/intervalo.")

    adapter = _make_adapter(strat, sl, tp)
    bt = FractionalBacktest(df, adapter, cash=cash, commission=0.001)
    stats = bt.run()
    print(stats)
    print("\nOperaciones:")
    cols = ["EntryTime", "ExitTime", "EntryPrice", "ExitPrice", "PnL", "ReturnPct"]
    print(stats["_trades"][cols].to_string())
    if plot:
        bt.plot(open_browser=False, filename=report_path)
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", default=settings.strategy, choices=list(STRATEGIES))
    ap.add_argument("--symbol", default=settings.symbol)
    ap.add_argument("--interval", default=settings.interval)
    ap.add_argument("--start", default="1 Jan 2024")
    ap.add_argument("--end", default=None)
    ap.add_argument("--cash", type=float, default=10_000)
    ap.add_argument("--sl", type=float, default=settings.stop_loss_pct)
    ap.add_argument("--tp", type=float, default=settings.take_profit_pct)
    ap.add_argument("--params", default="", help='ej: "fast_ma=50,slow_ma=200"')
    args = ap.parse_args()

    run_backtest(
        strategy_key=args.strategy,
        symbol=args.symbol,
        interval=args.interval,
        start=args.start,
        end=args.end,
        cash=args.cash,
        sl=args.sl,
        tp=args.tp,
        strategy_params=_parse_params(args.params),
    )


if __name__ == "__main__":
    main()
