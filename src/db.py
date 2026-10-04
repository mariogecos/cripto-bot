"""Persistencia local en PostgreSQL para posiciones y eventos de mercado."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from config import settings

log = logging.getLogger(__name__)


def build_position_record(
    *,
    symbol: str,
    qty: float,
    avg_entry_price: float,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    liquidation_reason: str | None = None,
    status: str = "open",
) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "qty": float(qty),
        "avg_entry_price": float(avg_entry_price),
        "stop_loss_price": float(stop_loss_price) if stop_loss_price is not None else None,
        "take_profit_price": float(take_profit_price) if take_profit_price is not None else None,
        "liquidation_reason": liquidation_reason,
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }


def build_market_event_record(
    *,
    symbol: str,
    interval: str,
    signal: str,
    price: float,
    strategy_name: str,
    stop_loss_price: float | None = None,
    take_profit_price: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "interval": interval,
        "signal": str(signal).upper(),
        "price": float(price),
        "strategy_name": strategy_name,
        "stop_loss_price": float(stop_loss_price) if stop_loss_price is not None else None,
        "take_profit_price": float(take_profit_price) if take_profit_price is not None else None,
        "note": note,
        "created_at": datetime.now(timezone.utc),
    }


class Database:
    """Wrapper mínimo para PostgreSQL local con tablas de posiciones y eventos."""

    def __init__(self) -> None:
        self.conn = None
        self.enabled = bool(settings.postgres_enabled and settings.postgres_dsn)
        if self.enabled:
            self._connect()

    def _connect(self) -> None:
        try:
            import psycopg

            self.conn = psycopg.connect(settings.postgres_dsn, autocommit=False)
        except Exception as exc:  # noqa: BLE001
            self.enabled = False
            self.conn = None
            log.warning("PostgreSQL no disponible; se deshabilita la persistencia local: %s", exc)

    def _ensure_connection(self) -> bool:
        if not self.enabled:
            return False
        if self.conn is None:
            self._connect()
        return self.conn is not None

    def init_db(self) -> None:
        if not self._ensure_connection():
            return

        with self.conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS crypto_positions (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    qty NUMERIC(20, 8) NOT NULL,
                    avg_entry_price NUMERIC(20, 8) NOT NULL,
                    stop_loss_price NUMERIC(20, 8),
                    take_profit_price NUMERIC(20, 8),
                    liquidation_reason VARCHAR(50),
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_crypto_positions_open_symbol
                ON crypto_positions(symbol)
                WHERE status = 'open';
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS market_history (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    interval VARCHAR(20) NOT NULL,
                    signal VARCHAR(20) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    strategy_name VARCHAR(100) NOT NULL,
                    stop_loss_price NUMERIC(20, 8),
                    take_profit_price NUMERIC(20, 8),
                    note VARCHAR(255),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS bot_initializations (
                    id SERIAL PRIMARY KEY,
                    bot_name VARCHAR(50) NOT NULL DEFAULT 'cripto-bot',
                    status VARCHAR(30) NOT NULL DEFAULT 'started',
                    symbol VARCHAR(20) NOT NULL,
                    interval VARCHAR(20) NOT NULL,
                    strategy_name VARCHAR(100) NOT NULL,
                    dry_run BOOLEAN NOT NULL DEFAULT TRUE,
                    note VARCHAR(255),
                    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        self.conn.commit()

    def upsert_open_position(
        self,
        *,
        symbol: str,
        qty: float,
        avg_entry_price: float,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        liquidation_reason: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._ensure_connection():
            return None

        row = build_position_record(
            symbol=symbol,
            qty=qty,
            avg_entry_price=avg_entry_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            liquidation_reason=liquidation_reason,
            status="open",
        )

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO crypto_positions (
                    symbol, qty, avg_entry_price, stop_loss_price, take_profit_price,
                    liquidation_reason, status, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'open', NOW())
                ON CONFLICT (symbol)
                WHERE status = 'open'
                DO UPDATE SET
                    qty = EXCLUDED.qty,
                    avg_entry_price = EXCLUDED.avg_entry_price,
                    stop_loss_price = EXCLUDED.stop_loss_price,
                    take_profit_price = EXCLUDED.take_profit_price,
                    liquidation_reason = EXCLUDED.liquidation_reason,
                    updated_at = NOW()
                ;
                """,
                (
                    row["symbol"],
                    row["qty"],
                    row["avg_entry_price"],
                    row["stop_loss_price"],
                    row["take_profit_price"],
                    row["liquidation_reason"],
                ),
            )
        self.conn.commit()
        return row

    def close_position(
        self,
        *,
        symbol: str,
        liquidation_reason: str | None = None,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
    ) -> dict[str, Any] | None:
        if not self._ensure_connection():
            return None

        row = build_position_record(
            symbol=symbol,
            qty=0.0,
            avg_entry_price=0.0,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            liquidation_reason=liquidation_reason,
            status="closed",
        )

        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE crypto_positions
                SET status = 'closed',
                    qty = 0,
                    avg_entry_price = 0,
                    stop_loss_price = %s,
                    take_profit_price = %s,
                    liquidation_reason = %s,
                    updated_at = NOW()
                WHERE symbol = %s AND status = 'open';
                """,
                (
                    row["stop_loss_price"],
                    row["take_profit_price"],
                    row["liquidation_reason"],
                    row["symbol"],
                ),
            )
        self.conn.commit()
        return row

    def record_market_event(
        self,
        symbol: str,
        interval: str,
        signal: str,
        price: float,
        strategy_name: str,
        *,
        stop_loss_price: float | None = None,
        take_profit_price: float | None = None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._ensure_connection():
            return None

        row = build_market_event_record(
            symbol=symbol,
            interval=interval,
            signal=signal,
            price=price,
            strategy_name=strategy_name,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            note=note,
        )

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO market_history (
                    symbol, interval, signal, price, strategy_name,
                    stop_loss_price, take_profit_price, note, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["symbol"],
                    row["interval"],
                    row["signal"],
                    row["price"],
                    row["strategy_name"],
                    row["stop_loss_price"],
                    row["take_profit_price"],
                    row["note"],
                    row["created_at"],
                ),
            )
        self.conn.commit()
        return row

    def record_bot_initialization(
        self,
        *,
        symbol: str,
        interval: str,
        strategy_name: str,
        dry_run: bool,
        status: str = "started",
        note: str | None = None,
    ) -> dict[str, Any] | None:
        if not self._ensure_connection():
            return None

        row = {
            "bot_name": "cripto-bot",
            "status": status,
            "symbol": symbol.upper(),
            "interval": interval,
            "strategy_name": strategy_name,
            "dry_run": bool(dry_run),
            "note": note,
            "started_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
        }

        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bot_initializations (
                    bot_name, status, symbol, interval, strategy_name,
                    dry_run, note, started_at, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    row["bot_name"],
                    row["status"],
                    row["symbol"],
                    row["interval"],
                    row["strategy_name"],
                    row["dry_run"],
                    row["note"],
                    row["started_at"],
                    row["created_at"],
                ),
            )
        self.conn.commit()
        return row


db = Database()


def get_db() -> Database:
    return db
