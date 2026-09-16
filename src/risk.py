"""Gestion de riesgo: tamano de posicion, stop-loss / take-profit y limite de perdida diaria."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class RiskManager:
    quote_per_trade: float
    stop_loss_pct: float
    take_profit_pct: float
    max_daily_loss: float

    _day: date = field(default_factory=date.today)
    _daily_pnl: float = 0.0

    def _roll_day(self) -> None:
        if date.today() != self._day:
            self._day = date.today()
            self._daily_pnl = 0.0

    def register_pnl(self, pnl: float) -> None:
        self._roll_day()
        self._daily_pnl += pnl

    def trading_allowed(self) -> bool:
        self._roll_day()
        return self._daily_pnl > -abs(self.max_daily_loss)

    def position_size(self, price: float, step_size: float) -> float:
        """Cantidad de moneda base a comprar, redondeada al step del par."""
        qty = self.quote_per_trade / price
        if step_size > 0:
            qty = math.floor(qty / step_size) * step_size
        return round(qty, 8)

    def stop_levels(self, entry_price: float) -> tuple[float, float]:
        sl = entry_price * (1 - self.stop_loss_pct)
        tp = entry_price * (1 + self.take_profit_pct)
        return round(sl, 2), round(tp, 2)
