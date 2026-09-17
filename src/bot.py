"""Loop principal del bot. Ejecuta la estrategia cada POLL_SECONDS.

Ejecutar:  python -m src.bot
"""
from __future__ import annotations

import logging
import time

from config import settings
from src import notify
from src.data import klines_to_df
from src.exchange import Exchange
from src.executor import Executor
from src.risk import RiskManager
from src.strategy import strategy_from_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("bot")


def run() -> None:
    ex = Exchange()
    risk = RiskManager(
        quote_per_trade=settings.quote_per_trade,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        max_daily_loss=settings.max_daily_loss,
    )
    executor = Executor(ex, risk)
    strat = strategy_from_settings(settings)

    modo = "DRY_RUN" if settings.dry_run else "REAL"
    notify.send(
        f"Bot en funcionamiento | {settings.symbol} {settings.interval} | "
        f"estrategia {strat.key} | modo {modo}"
    )

    # Cuantas velas pedimos: suficientes para que el indicador mas largo tenga datos.
    lookback = max(settings.slow_ma * 3, 200)

    while True:
        try:
            raw = ex.get_klines(settings.symbol, settings.interval, limit=lookback)
            df = klines_to_df(raw)
            # La ultima vela aun no cerro: la descartamos para operar solo con datos firmes.
            df = df.iloc[:-1]

            price = ex.get_price(settings.symbol)
            signal = strat.signal(df)
            log.info("precio=%.2f senal=%s", price, signal.value)
            executor.handle(signal, price)
        except Exception as exc:  # noqa: BLE001
            log.exception("Error en el loop: %s", exc)

        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    run()
