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

    def get_account_balances(self) -> dict[str, dict[str, float]]:
        """Devuelve saldos disponibles y bloqueados por activo de la cuenta."""
        account = self.client.get_account()
        snapshot: dict[str, dict[str, float]] = {}
        for item in account.get("balances", []):
            asset = item.get("asset")
            if not asset:
                continue
            free = float(item.get("free", 0.0) or 0.0)
            locked = float(item.get("locked", 0.0) or 0.0)
            snapshot[asset] = {
                "free": free,
                "locked": locked,
                "total": free + locked,
            }
        return snapshot

    def get_total_portfolio_value_usdt(self) -> float:
        """Suma el valor total de todos los activos de la cuenta en USDT.

        Incluye saldo spot, margin, futures y otros productos que Binance expone en la
        API de la cuenta, sin limitarse a la wallet spot.
        """
        balances: dict[str, float] = {}

        def add_balance(asset: str, qty: float) -> None:
            if not asset:
                return
            asset_name = str(asset).upper()
            balances[asset_name] = balances.get(asset_name, 0.0) + float(qty or 0.0)

        # Wallet spot (la que venía en la app)
        for asset, payload in self.get_account_balances().items():
            add_balance(asset, payload.get("total", 0.0))

        # Margin account (si existe)
        try:
            margin_account = self.client.get_margin_account()
            for item in margin_account.get("userAssets", []):
                asset = item.get("asset")
                qty = item.get("netAsset")
                if qty is None:
                    qty = item.get("free")
                add_balance(asset, qty)
        except Exception:  # pragma: no cover - depende del permiso del usuario
            pass

        # Futures account (si existe)
        try:
            futures_account = self.client.get_futures_account()
            for item in futures_account.get("assets", []):
                if "walletBalance" in item:
                    add_balance(item.get("asset"), item.get("walletBalance"))
        except Exception:  # pragma: no cover - depende del permiso del usuario
            pass

        # Snapshots por tipo de cuenta (spot/margin/futures), si están habilitados.
        for account_type in ("SPOT", "MARGIN", "FUTURES"):
            try:
                snapshot = self.client.get_account_snapshot(type=account_type)
            except Exception:
                continue
            for item in snapshot.get("snapshotVos", []):
                data = item.get("data", {})
                for bal in data.get("balances", []):
                    add_balance(bal.get("asset"), bal.get("free", 0.0) + bal.get("locked", 0.0))

        # Earn / savings / lending cuando la versión del cliente expone ese endpoint.
        for method_name in (
            "get_lending_account",
            "get_savings_account",
            "get_lending_product_position",
            "get_flexible_product_position",
        ):
            method = getattr(self.client, method_name, None)
            if not method:
                continue
            try:
                payload = method()
            except Exception:
                continue
            if not payload:
                continue
            if isinstance(payload, dict):
                for item in payload.get("positionVos", []) or payload.get("records", []) or payload.get("list", []):
                    asset = item.get("asset") or item.get("coin") or item.get("productId")
                    value = item.get("amount") or item.get("totalAmount") or item.get("balance") or item.get("total" )
                    add_balance(asset, value)
                if "assets" in payload:
                    for item in payload["assets"]:
                        add_balance(item.get("asset"), item.get("free") or item.get("amount") or item.get("totalAmount"))

        if not balances:
            return 0.0

        tickers = self.client.get_all_tickers()
        price_by_symbol: dict[str, float] = {}
        for ticker in tickers:
            symbol = str(ticker.get("symbol", "")).upper()
            if not symbol.endswith("USDT"):
                continue
            price = float(ticker.get("price", 0.0) or 0.0)
            if price > 0:
                price_by_symbol[symbol[:-4]] = price

        total_usdt = 0.0
        for asset, qty in balances.items():
            asset_name = str(asset).upper()
            if asset_name in {"USDT", "BUSD", "USDC", "TUSD", "FDUSD", "DAI"}:
                total_usdt += qty
                continue
            if asset_name in price_by_symbol:
                total_usdt += qty * price_by_symbol[asset_name]
                continue
            if asset_name == "BTC":
                total_usdt += qty * price_by_symbol.get("BTC", 0.0)

        return round(total_usdt, 2)

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
