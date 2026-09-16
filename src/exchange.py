"""Wrapper delgado sobre python-binance con soporte de testnet."""
from __future__ import annotations

import logging

from binance.client import Client

from config import settings

log = logging.getLogger(__name__)


class Exchange:
    def __init__(self) -> None:
        self.client = Client(
            settings.binance_api_key,
            settings.binance_api_secret,
            testnet=settings.binance_testnet,
        )
        modo = "TESTNET" if settings.binance_testnet else "PRODUCCION"
        log.info("Cliente Binance inicializado en modo %s", modo)

    # --- Datos de mercado ---
    def get_klines(self, symbol: str, interval: str, limit: int = 500):
        return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)

    def get_price(self, symbol: str) -> float:
        return float(self.client.get_symbol_ticker(symbol=symbol)["price"])

    # --- Cuenta ---
    def get_free_balance(self, asset: str) -> float:
        bal = self.client.get_asset_balance(asset=asset)
        return float(bal["free"]) if bal else 0.0

    # --- Ordenes ---
    def market_buy(self, symbol: str, quote_amount: float):
        """Compra a mercado gastando `quote_amount` de la moneda cotizada (ej. USDT)."""
        return self.client.order_market_buy(
            symbol=symbol, quoteOrderQty=round(quote_amount, 2)
        )

    def market_sell(self, symbol: str, quantity: float):
        """Vende a mercado `quantity` de la moneda base (ej. BTC)."""
        return self.client.order_market_sell(symbol=symbol, quantity=quantity)

    def get_symbol_filters(self, symbol: str) -> dict:
        info = self.client.get_symbol_info(symbol)
        return {f["filterType"]: f for f in info["filters"]}
