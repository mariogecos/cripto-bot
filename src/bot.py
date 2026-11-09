"""Loop principal del bot. Ejecuta la estrategia cada POLL_SECONDS.

Ejecutar:  python -m src.bot
"""
from __future__ import annotations

import logging
import math
import time

import requests

from config import settings
from src import notify
from src.data import klines_to_df
from src.db import get_db
from src.exchange import Exchange
from src.executor import Executor
from src.risk import RiskManager
from src.strategy import strategy_from_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
log = logging.getLogger("bot")
_last_binance_ip_alert: str | None = None


def _get_public_ip() -> str | None:
    for url in ("https://api.ipify.org", "https://checkip.amazonaws.com"):
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            ip_value = response.text.strip()
            if ip_value:
                return ip_value
        except Exception as exc:  # noqa: BLE001
            log.warning("No se pudo consultar la IP pública desde %s: %s", url, exc)
    return None


def ensure_binance_ip_registry() -> tuple[str | None, str | None]:
    """Guarda la IP actual y avisa por Telegram si cambió respecto de la guardada."""
    db = get_db()
    db.init_db()
    current_ip = _get_public_ip()
    if not current_ip:
        log.warning("No se pudo resolver la IP pública del servidor. Se omite validacion de whitelist.")
        return None, None

    if not db.enabled:
        log.warning("PostgreSQL no disponible. No se guardó la IP del servidor ni se pudo validar la whitelist de Binance.")
        return current_ip, db.get_saved_binance_ip()

    stored_ip = db.get_saved_binance_ip()
    global _last_binance_ip_alert

    if not stored_ip:
        result = db.save_binance_ip(current_ip)
        if result is None:
            log.warning("No se pudo guardar la IP actual del servidor en la DB: %s", current_ip)
            return current_ip, stored_ip
        log.info("Se guardó la IP actual del servidor en la DB: %s", current_ip)
        message = f"IP BINANCE REGISTRADA | servidor={current_ip} | se guardó la IP actual en la DB."
        if _last_binance_ip_alert != current_ip:
            notify.send(message)
            _last_binance_ip_alert = current_ip
        return current_ip, stored_ip

    if current_ip != stored_ip:
        result = db.save_binance_ip(current_ip)
        if result is None:
            log.warning("No se pudo actualizar la IP actual del servidor en la DB: %s", current_ip)
            return current_ip, stored_ip
        message = (
            f"ALERTA IP BINANCE | IP actual del servidor: {current_ip} | IP guardada: {stored_ip} | "
            "actualizá la whitelist de Binance."
        )
        if _last_binance_ip_alert != current_ip:
            notify.send(message)
            _last_binance_ip_alert = current_ip
        log.warning(message)
        return current_ip, stored_ip

    _last_binance_ip_alert = None
    return current_ip, stored_ip


def quote_asset_for(symbol: str) -> str:
    for quote in ("USDT", "BUSD", "USDC", "BTC", "ETH"):
        if symbol.endswith(quote):
            return quote
    return symbol[-4:] if len(symbol) >= 4 else symbol


def run_minimum_trade_smoke_test(symbol: str | None = None, wait_seconds: int = 60) -> dict[str, float | str]:
    """Compra un monto mínimo del par, espera un minuto y luego lo vende.
    Sirve para validar que la conexión con Binance, la DB y Telegram funcionan."""
    db = get_db()
    db.init_db()
    if not db.enabled:
        log.warning("PostgreSQL no disponible. No se persistirá la compra/prueba ni la venta del smoke test.")
    symbol = (symbol or settings.symbol).upper()
    ex = Exchange()
    quote_asset = quote_asset_for(symbol)
    base_asset = symbol[: -len(quote_asset)] if quote_asset else symbol

    filters = ex.get_symbol_filters(symbol)
    step_size = float(filters.get("LOT_SIZE", {}).get("stepSize", 0.0) or 0.0)
    min_qty = float(filters.get("LOT_SIZE", {}).get("minQty", 0.0) or 0.0)
    min_notional = float(filters.get("MIN_NOTIONAL", {}).get("minNotional", 0.0) or 0.0)
    buy_price = ex.get_price(symbol)

    qty_from_min_qty = (min_qty * buy_price) if min_qty > 0 else 0.0
    quote_amount = max(min_notional, qty_from_min_qty, 10.0)
    quote_amount = round(quote_amount, 2)

    qty = quote_amount / buy_price
    if step_size > 0:
        qty = math.floor(qty / step_size) * step_size
    qty = round(qty, 8)
    if qty <= 0:
        raise ValueError(f"No se pudo calcular una cantidad válida para {symbol}")

    try:
        free_quote = ex.get_free_balance(quote_asset)
        free_base = ex.get_free_balance(base_asset) if base_asset else 0.0
        log.info(
            "Saldo disponible antes de la compra: %s=%.8f | %s=%.8f | monto de prueba=%s %.2f",
            quote_asset,
            free_quote,
            base_asset,
            free_base,
            quote_asset,
            quote_amount,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo consultar saldo antes del smoke test: %s", exc)

    ex.market_buy(symbol, quote_amount)
    db.record_market_event(
        symbol=symbol,
        interval="1m",
        signal="BUY",
        price=buy_price,
        strategy_name="smoke_test",
        note=f"smoke-test-compra-minima-{quote_asset}",
    )
    db.upsert_open_position(
        symbol=symbol,
        qty=qty,
        avg_entry_price=buy_price,
        liquidation_reason="smoke-test-buy",
    )
    notify.send(
        f"SMOKE TEST BUY | {symbol} | monto mínimo Binance = {quote_amount:.2f} {quote_asset} "
        f"(~ {qty:.8f} {base_asset}) @ {buy_price:.2f}"
    )
    log.info("SMOKE TEST BUY: %s %s @ %.2f", qty, base_asset, buy_price)

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    try:
        free_base_balance = ex.get_free_balance(base_asset) if base_asset else 0.0
    except Exception as exc:  # noqa: BLE001
        free_base_balance = 0.0
        log.warning("No se pudo consultar el saldo de %s antes de vender: %s", base_asset, exc)

    sell_price = ex.get_price(symbol)
    fee_tolerance = max(1e-8, qty * 0.001)
    sell_quantity = min(free_base_balance, qty)

    if free_base_balance < (qty - fee_tolerance):
        message = (
            f"SMOKE TEST SKIP SELL | {symbol} | saldo insuficiente en {base_asset}: "
            f"disponible={free_base_balance:.8f}, requerido={qty:.8f} (tolerancia={fee_tolerance:.8f})"
        )
        log.warning(message)
        notify.send(message)
        return {
            "symbol": symbol,
            "base_asset": base_asset,
            "quote_asset": quote_asset,
            "quote_amount": float(quote_amount),
            "qty": float(qty),
            "sell_quantity": float(sell_quantity),
            "buy_price": float(buy_price),
            "sell_price": float(sell_price),
            "wait_seconds": int(wait_seconds),
            "sold": False,
            "reason": "insufficient_base_balance",
        }

    ex.market_sell(symbol, sell_quantity)
    db.record_market_event(
        symbol=symbol,
        interval="1m",
        signal="SELL",
        price=sell_price,
        strategy_name="smoke_test",
        note=f"smoke-test-venta-minima-{quote_asset}",
    )
    db.close_position(symbol=symbol, liquidation_reason="smoke-test-sell")
    notify.send(
        f"SMOKE TEST SELL | {symbol} | vendió {sell_quantity:.8f} {base_asset} @ {sell_price:.2f}"
    )
    log.info("SMOKE TEST SELL: %s %s @ %.2f", sell_quantity, base_asset, sell_price)

    return {
        "symbol": symbol,
        "base_asset": base_asset,
        "quote_asset": quote_asset,
        "quote_amount": float(quote_amount),
        "qty": float(qty),
        "sell_quantity": float(sell_quantity),
        "buy_price": float(buy_price),
        "sell_price": float(sell_price),
        "wait_seconds": int(wait_seconds),
        "sold": True,
    }


def run() -> None:
    db = get_db()
    db.init_db()
    ensure_binance_ip_registry()
    db.record_bot_initialization(
        symbol=settings.symbol,
        interval=settings.interval,
        strategy_name=strategy_from_settings(settings).key,
        dry_run=settings.dry_run,
        note="Bot arrancado",
    )

    ex = Exchange()
    quote_asset = quote_asset_for(settings.symbol)
    base_asset = settings.symbol[: -len(quote_asset)] if quote_asset else settings.symbol
    try:
        account_balances = ex.get_account_balances()
        quote_balance = ex.get_free_balance(quote_asset)
        base_balance = ex.get_free_balance(base_asset) if base_asset else 0.0
        if account_balances:
            balance_parts = [
                f"{asset}={payload['free']:.8f} (locked={payload['locked']:.8f})"
                for asset, payload in sorted(account_balances.items())
            ]
            log.info("Saldo real en Binance: %s", " | ".join(balance_parts))
    except Exception as exc:  # noqa: BLE001
        quote_balance = 0.0
        base_balance = 0.0
        account_balances = {}
        log.warning(
            "No se pudo consultar el saldo de Binance. Verificá API key, IP y permisos de la cuenta. Error: %s",
            exc,
        )
        notify.send(
            "No se pudo consultar el saldo disponible en Binance. Revisa API key, IP y permisos."
        )

    trade_budget = settings.quote_per_trade if settings.quote_per_trade > 0 else 0.0
    estimate_trades = quote_balance / trade_budget if trade_budget > 0 else 0.0
    total_portfolio_usdt = ex.get_total_portfolio_value_usdt()

    current_ip, _ = ensure_binance_ip_registry()
    log.info(
        "ARRANQUE | ip=%s | %s=%0.2f | %s=%0.8f | total=%0.2f USDT | budget=%0.2f | ops~%.1f | signal=%s",
        current_ip or "unknown",
        quote_asset,
        quote_balance,
        base_asset,
        base_balance,
        total_portfolio_usdt,
        trade_budget,
        estimate_trades,
        "HOLD",
    )
    notify.send(
        f"ARRANQUE | ip={current_ip or 'unknown'} | {settings.symbol} {settings.interval} | "
        f"{strategy_from_settings(settings).key} | {'DRY_RUN' if settings.dry_run else 'REAL'} | "
        f"{quote_asset}={quote_balance:.2f} | {base_asset}={base_balance:.8f} | total={total_portfolio_usdt:.2f} USDT | signal=HOLD"
    )

    risk = RiskManager(
        quote_per_trade=settings.quote_per_trade,
        stop_loss_pct=settings.stop_loss_pct,
        take_profit_pct=settings.take_profit_pct,
        max_daily_loss=settings.max_daily_loss,
    )
    executor = Executor(ex, risk)
    strat = strategy_from_settings(settings)

    modo = "DRY_RUN" if settings.dry_run else "REAL"
    current_ip, _ = ensure_binance_ip_registry()
    notify.send(
        f"ARRANQUE | ip={current_ip or 'unknown'} | {settings.symbol} {settings.interval} | {strat.key} | {modo} | "
        f"{base_asset}={base_balance:.8f} | {quote_asset}={quote_balance:.2f} | total={total_portfolio_usdt:.2f} USDT | signal=HOLD"
    )

    # Cuantas velas pedimos: suficientes para que el indicador mas largo tenga datos.
    lookback = max(settings.slow_ma * 3, 200)

    while True:
        try:
            ensure_binance_ip_registry()
            raw = ex.get_klines(settings.symbol, settings.interval, limit=lookback)
            df = klines_to_df(raw)
            # La ultima vela aun no cerro: la descartamos para operar solo con datos firmes.
            df = df.iloc[:-1]

            price = ex.get_price(settings.symbol)
            signal = strat.signal(df)
            sl, tp = risk.stop_levels(price)
            db.record_market_event(
                settings.symbol,
                settings.interval,
                signal.value,
                price,
                strat.key,
                stop_loss_price=sl,
                take_profit_price=tp,
            )
            current_ip, _ = ensure_binance_ip_registry()
            account_balances = ex.get_account_balances()
            quote_balance = ex.get_free_balance(quote_asset)
            base_balance = ex.get_free_balance(base_asset) if base_asset else 0.0
            total_portfolio_usdt = ex.get_total_portfolio_value_usdt()
            log.info(
                "precio=%.2f | ip=%s | %s=%0.2f | %s=%0.8f | total=%0.2f USDT | signal=%s",
                price,
                current_ip or "unknown",
                quote_asset,
                quote_balance,
                base_asset,
                base_balance,
                total_portfolio_usdt,
                signal.value,
            )
            executor.handle(signal, price)
        except Exception as exc:  # noqa: BLE001
            log.exception("Error en el loop: %s", exc)

        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    run()
