"""Inicializa PostgreSQL y crea todas las tablas requeridas por el bot."""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings


def parse_dsn(dsn: str):
    if not dsn:
        raise ValueError("POSTGRES_DSN vacío. Configurá la URL de la base de datos en .env")

    parsed = urlparse(dsn)
    if parsed.scheme not in {"postgresql", "postgres"}:
        raise ValueError(f"POSTGRES_DSN inválida: {dsn}")

    dbname = (parsed.path or "/").lstrip("/") or "postgres"
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    user = parsed.username or "postgres"
    password = parsed.password or ""

    return host, port, dbname, user, password


def ensure_database_exists(dsn: str) -> str:
    host, port, dbname, user, password = parse_dsn(dsn)

    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "No está instalado psycopg. Ejecutá: pip install psycopg[binary]"
        ) from exc

    admin_dsn = f"postgresql://{user}:{password}@{host}:{port}/postgres"
    conn = psycopg.connect(admin_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            exists = cur.fetchone()
            if not exists:
                quoted = '"' + dbname.replace('"', '""') + '"'
                cur.execute(f"CREATE DATABASE {quoted}")
                print(f"Base de datos creada: {dbname}")
    finally:
        conn.close()

    return dsn


def create_all_tables(dsn: str) -> None:
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "No está instalado psycopg. Ejecutá: pip install psycopg[binary]"
        ) from exc

    conn = psycopg.connect(dsn, autocommit=False)
    try:
        with conn.cursor() as cur:
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
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS binance_ip_registry (
                    id SERIAL PRIMARY KEY,
                    ip_address VARCHAR(45) NOT NULL UNIQUE,
                    source VARCHAR(50) NOT NULL DEFAULT 'public_ip',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS trade_history (
                    id SERIAL PRIMARY KEY,
                    symbol VARCHAR(20) NOT NULL,
                    side VARCHAR(10) NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    qty NUMERIC(20, 8) NOT NULL,
                    price NUMERIC(20, 8) NOT NULL,
                    quote_amount NUMERIC(20, 8) NOT NULL,
                    strategy_name VARCHAR(100),
                    note VARCHAR(255),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                """
            )
        conn.commit()
        print("Tablas creadas correctamente.")
    finally:
        conn.close()


if __name__ == "__main__":
    try:
        dsn = settings.postgres_dsn
        if not dsn:
            raise ValueError("Falta POSTGRES_DSN en .env")

        ensure_database_exists(dsn)
        create_all_tables(dsn)
        print("Inicialización de PostgreSQL completada.")
    except Exception as exc:  # noqa: BLE001
        print(f"Error al inicializar la base de datos: {exc}")
        raise SystemExit(1)
