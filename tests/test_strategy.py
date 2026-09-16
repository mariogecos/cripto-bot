import numpy as np
import pandas as pd

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
