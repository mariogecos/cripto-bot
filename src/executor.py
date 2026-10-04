"""Traduce senales de la estrategia en ordenes reales (o simuladas si DRY_RUN)."""
from __future__ import annotations

import logging

from config import settings
from src import notify
from src.db import get_db
from src.exchange import Exchange
from src.risk import RiskManager
from src.strategy import Signal

log = logging.getLogger(__name__)


class Position:
    def __init__(self) -> None:
        self.open = False
        self.qty = 0.0
        self.entry = 0.0
        self.sl = 0.0
        self.tp = 0.0


class Executor:
    def __init__(self, exchange: Exchange, risk: RiskManager) -> None:
        self.ex = exchange
        self.risk = risk
        self.db = get_db()
        self.pos = Position()
        self.base, self.quote = self._split_symbol(settings.symbol)
        self._step = self._load_step_size(settings.symbol)

    @staticmethod
    def _split_symbol(symbol: str) -> tuple[str, str]:
        for q in ("USDT", "BUSD", "USDC", "BTC", "ETH"):
            if symbol.endswith(q):
                return symbol[: -len(q)], q
        return symbol[:-4], symbol[-4:]

    def _load_step_size(self, symbol: str) -> float:
        try:
            filters = self.ex.get_symbol_filters(symbol)
            return float(filters["LOT_SIZE"]["stepSize"])
        except Exception:  # noqa: BLE001
            return 0.0

    def handle(self, signal: Signal, price: float) -> None:
        if not self.risk.trading_allowed():
            log.warning("Limite de perdida diaria alcanzado. No se opera.")
            return

        if signal is Signal.BUY and not self.pos.open:
            self._open(price)
        elif signal is Signal.SELL and self.pos.open:
            self._close(price, motivo="senal SELL")
        elif self.pos.open:
            self._check_stops(price)

    def _open(self, price: float) -> None:
        qty = self.risk.position_size(price, self._step)
        if qty <= 0:
            log.warning("Tamano de posicion 0; se omite compra.")
            return
        sl, tp = self.risk.stop_levels(price)
        if settings.dry_run:
            log.info(
                "[DRY_RUN] COMPRA %s %s @ %.2f (SL %.2f / TP %.2f)",
                qty, self.base, price, sl, tp,
            )
        else:
            self.ex.market_buy(settings.symbol, settings.quote_per_trade)
        self.pos.open = True
        self.pos.qty = qty
        self.pos.entry = price
        self.pos.sl, self.pos.tp = sl, tp
        self.db.upsert_open_position(
            symbol=settings.symbol,
            qty=qty,
            avg_entry_price=price,
            stop_loss_price=sl,
            take_profit_price=tp,
            liquidation_reason="risk-levels",
        )
        notify.send(f"COMPRA {settings.symbol} @ {price:.2f} | SL {sl:.2f} TP {tp:.2f}")

    def _close(self, price: float, motivo: str) -> None:
        pnl = (price - self.pos.entry) * self.pos.qty
        if settings.dry_run:
            log.info(
                "[DRY_RUN] VENTA %s %s @ %.2f | PnL %.2f (%s)",
                self.pos.qty, self.base, price, pnl, motivo,
            )
        else:
            self.ex.market_sell(settings.symbol, self.pos.qty)
        self.risk.register_pnl(pnl)
        self.db.close_position(
            symbol=settings.symbol,
            liquidation_reason=motivo,
            stop_loss_price=self.pos.sl,
            take_profit_price=self.pos.tp,
        )
        notify.send(f"VENTA {settings.symbol} @ {price:.2f} | PnL {pnl:.2f} | {motivo}")
        self.pos = Position()

    def _check_stops(self, price: float) -> None:
        if price <= self.pos.sl:
            self._close(price, motivo="stop-loss")
        elif price >= self.pos.tp:
            self._close(price, motivo="take-profit")
