import numpy as np
import pandas as pd

from src.db import Database, build_market_event_record, build_position_record
from src.strategy import STRATEGIES, Signal, SmaCrossRsi, build_strategy


def _df_from_prices(prices):
    idx = pd.date_range("2023-01-01", periods=len(prices), freq="h")
    return pd.DataFrame(
        {"open": prices, "high": prices, "low": prices, "close": prices, "volume": 1.0},
        index=idx,
    )


def test_registry_tiene_las_estrategias():
    assert "sma_cross_rsi" in STRATEGIES
    assert "rsi_reversion" in STRATEGIES


def test_compute_devuelve_columnas_de_senal():
    df = _df_from_prices(np.linspace(100, 130, 200))
    out = SmaCrossRsi().compute(df)
    assert {"entry", "exit", "fast", "slow", "rsi"} <= set(out.columns)
    assert out["entry"].dtype == bool and out["exit"].dtype == bool


def test_hold_con_pocos_datos():
    df = _df_from_prices(np.ones(10))
    assert SmaCrossRsi().signal(df) is Signal.HOLD


def test_signal_es_enum_valido():
    prices = np.concatenate([np.linspace(100, 80, 60), np.linspace(80, 130, 60)])
    sig = build_strategy("sma_cross_rsi", fast_ma=5, slow_ma=20).signal(_df_from_prices(prices))
    assert sig in (Signal.BUY, Signal.SELL, Signal.HOLD)


def test_parametro_invalido_falla():
    try:
        build_strategy("sma_cross_rsi", no_existe=1)
    except ValueError:
        return
    raise AssertionError("deberia haber lanzado ValueError")


def test_build_position_record_incluye_valor_compra_y_liquidacion():
    row = build_position_record(
        symbol="BTCUSDT",
        qty=0.2,
        avg_entry_price=65000.0,
        stop_loss_price=62000.0,
        take_profit_price=71000.0,
        liquidation_reason="take-profit",
    )

    assert row["symbol"] == "BTCUSDT"
    assert row["qty"] == 0.2
    assert row["avg_entry_price"] == 65000.0
    assert row["stop_loss_price"] == 62000.0
    assert row["take_profit_price"] == 71000.0
    assert row["liquidation_reason"] == "take-profit"
    assert row["status"] == "open"


def test_build_market_event_record_guarda_la_senal_del_mercado():
    row = build_market_event_record(
        symbol="ETHUSDT",
        interval="1h",
        signal="BUY",
        price=3500.0,
        strategy_name="sma_cross_rsi",
        stop_loss_price=3300.0,
        take_profit_price=3800.0,
    )

    assert row["symbol"] == "ETHUSDT"
    assert row["interval"] == "1h"
    assert row["signal"] == "BUY"
    assert row["price"] == 3500.0
    assert row["strategy_name"] == "sma_cross_rsi"
    assert row["stop_loss_price"] == 3300.0
    assert row["take_profit_price"] == 3800.0


def test_init_db_crea_tabla_de_inicializaciones_del_bot():
    executed = []

    class DummyCursor:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def execute(self, query, params=None):
            executed.append((query.strip(), params))

    class DummyConnection:
        def cursor(self):
            return DummyCursor()

        def commit(self):
            return None

    db = Database()
    db.enabled = True
    db.conn = DummyConnection()

    db.init_db()

    assert any("CREATE TABLE IF NOT EXISTS bot_initializations" in query for query, _ in executed)
