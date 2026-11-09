import numpy as np
import pandas as pd

import src.executor as executor_module
from src.bot import ensure_binance_ip_registry, quote_asset_for, run_minimum_trade_smoke_test
from src.db import Database, build_market_event_record, build_position_record
from src.executor import Executor
from src.risk import RiskManager
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


def test_quote_asset_for_detecta_la_moneda_cotizada():
    assert quote_asset_for("BTCUSDT") == "USDT"
    assert quote_asset_for("ETHBTC") == "BTC"
    assert quote_asset_for("SOLUSDT") == "USDT"


def test_total_portfolio_value_en_usdt_suma_todos_los_activos(monkeypatch):
    class DummyClient:
        def get_account(self):
            return {
                "balances": [
                    {"asset": "USDT", "free": "200.0", "locked": "50.0"},
                    {"asset": "BTC", "free": "1.0", "locked": "0.0"},
                    {"asset": "ETH", "free": "2.0", "locked": "0.0"},
                ]
            }

        def get_margin_account(self):
            return {"userAssets": [{"asset": "SOL", "netAsset": "2.0"}]}

        def get_futures_account(self):
            return {"assets": [{"asset": "USDT", "walletBalance": "100.0"}]}

        def get_all_tickers(self):
            return [
                {"symbol": "BTCUSDT", "price": "60000"},
                {"symbol": "ETHUSDT", "price": "3000"},
                {"symbol": "SOLUSDT", "price": "100"},
            ]

        def get_account_snapshot(self, **kwargs):
            return {"snapshotVos": []}

    monkeypatch.setattr("src.exchange.Client", lambda *args, **kwargs: DummyClient())

    ex = __import__("src.exchange", fromlist=["Exchange"]).Exchange()
    total = ex.get_total_portfolio_value_usdt()

    assert total == 200.0 + 50.0 + 60000.0 + 6000.0 + 200.0


def test_ensure_binance_ip_registry_envia_alerta_al_guardar_y_cambiar_ip(monkeypatch):
    calls = []

    class DummyDB:
        def __init__(self):
            self.saved = None
        def init_db(self):
            return None
        def get_saved_binance_ip(self):
            return self.saved
        def save_binance_ip(self, ip):
            self.saved = ip
            calls.append(("save", ip))
            return ip

    monkeypatch.setattr("src.bot.get_db", lambda: DummyDB())
    monkeypatch.setattr("src.bot._get_public_ip", lambda: "167.60.136.185")
    monkeypatch.setattr("src.bot.notify.send", lambda msg: calls.append(("notify", msg)))

    ensure_binance_ip_registry()
    assert any(kind == "notify" for kind, _ in calls)

    dummy_db = DummyDB()
    dummy_db.saved = "167.60.136.184"
    monkeypatch.setattr("src.bot.get_db", lambda: dummy_db)
    monkeypatch.setattr("src.bot._get_public_ip", lambda: "167.60.136.185")
    calls.clear()

    ensure_binance_ip_registry()
    assert any(kind == "notify" for kind, _ in calls)


def test_run_minimum_trade_smoke_test_hace_compra_y_venta_de_prueba(monkeypatch):
    calls = []

    class DummyDB:
        def __init__(self):
            self.events = []
        def init_db(self):
            return None
        def record_market_event(self, symbol, interval, signal, price, strategy_name, **kwargs):
            self.events.append({"signal": signal, "price": price, "note": kwargs.get("note")})
            calls.append(("event", symbol, signal, price, kwargs.get("note")))
            return {"signal": signal}
        def upsert_open_position(self, **kwargs):
            calls.append(("open", kwargs["symbol"], kwargs["qty"]))
            return {"ok": True}
        def close_position(self, **kwargs):
            calls.append(("close", kwargs["symbol"], kwargs["liquidation_reason"]))
            return {"ok": True}

    class DummyExchange:
        def __init__(self):
            self.base_bal = 0.00012
        def get_symbol_filters(self, symbol):
            return {"LOT_SIZE": {"stepSize": 0.000001, "minQty": 0.00001}, "MIN_NOTIONAL": {"minNotional": 10.0}}
        def get_free_balance(self, asset):
            if asset == "USDT":
                return 100.0
            if asset == "BTC":
                return self.base_bal
            return 0.0
        def market_buy(self, symbol, quote_amount):
            calls.append(("buy", symbol, quote_amount))
            self.base_bal += quote_amount / 60000.0
            return {"status": "filled"}
        def market_sell(self, symbol, quantity):
            calls.append(("sell", symbol, quantity))
            self.base_bal -= quantity
            return {"status": "filled"}
        def get_price(self, symbol):
            return 60000.0

    monkeypatch.setattr("src.bot.Exchange", lambda: DummyExchange())
    monkeypatch.setattr("src.bot.get_db", lambda: DummyDB())
    monkeypatch.setattr("src.bot.notify.send", lambda msg: calls.append(("notify", msg)))
    monkeypatch.setattr("src.bot.time.sleep", lambda s: None)

    result = run_minimum_trade_smoke_test(symbol="BTCUSDT", wait_seconds=0)

    assert result["symbol"] == "BTCUSDT"
    assert result["quote_amount"] == 10.0
    assert result["sold"] is True
    assert any(call[0] == "buy" for call in calls)
    assert any(call[0] == "sell" for call in calls)
    assert any(call[0] == "notify" for call in calls)


def test_run_minimum_trade_smoke_test_skipa_venta_si_no_hay_btc(monkeypatch):
    calls = []

    class DummyDB:
        def init_db(self):
            return None
        def record_market_event(self, *args, **kwargs):
            return {"ok": True}
        def upsert_open_position(self, *args, **kwargs):
            return {"ok": True}
        def close_position(self, *args, **kwargs):
            return {"ok": True}

    class DummyExchange:
        def get_symbol_filters(self, symbol):
            return {"LOT_SIZE": {"stepSize": 0.000001, "minQty": 0.00001}, "MIN_NOTIONAL": {"minNotional": 10.0}}
        def get_free_balance(self, asset):
            if asset == "USDT":
                return 100.0
            return 0.0
        def market_buy(self, symbol, quote_amount):
            calls.append(("buy", symbol, quote_amount))
            return {"status": "filled"}
        def market_sell(self, symbol, quantity):
            calls.append(("sell", symbol, quantity))
            raise AssertionError("no debería vender si no hay BTC")
        def get_price(self, symbol):
            return 60000.0

    monkeypatch.setattr("src.bot.Exchange", lambda: DummyExchange())
    monkeypatch.setattr("src.bot.get_db", lambda: DummyDB())
    monkeypatch.setattr("src.bot.notify.send", lambda msg: calls.append(("notify", msg)))
    monkeypatch.setattr("src.bot.time.sleep", lambda s: None)

    result = run_minimum_trade_smoke_test(symbol="BTCUSDT", wait_seconds=0)

    assert result["sold"] is False
    assert result["reason"] == "insufficient_base_balance"
    assert any(call[0] == "notify" for call in calls)


def test_run_minimum_trade_smoke_test_permite_venta_con_fee_minoritaria(monkeypatch):
    calls = []

    class DummyDB:
        def init_db(self):
            return None
        def record_market_event(self, *args, **kwargs):
            return {"ok": True}
        def upsert_open_position(self, *args, **kwargs):
            return {"ok": True}
        def close_position(self, *args, **kwargs):
            return {"ok": True}

    class DummyExchange:
        def __init__(self):
            self.base_bal = 0.00011988
        def get_symbol_filters(self, symbol):
            return {"LOT_SIZE": {"stepSize": 0.000001, "minQty": 0.00001}, "MIN_NOTIONAL": {"minNotional": 10.0}}
        def get_free_balance(self, asset):
            if asset == "USDT":
                return 100.0
            if asset == "BTC":
                return self.base_bal
            return 0.0
        def market_buy(self, symbol, quote_amount):
            calls.append(("buy", symbol, quote_amount))
            self.base_bal += quote_amount / 60000.0
            return {"status": "filled"}
        def market_sell(self, symbol, quantity):
            calls.append(("sell", symbol, quantity))
            self.base_bal -= quantity
            return {"status": "filled"}
        def get_price(self, symbol):
            return 60000.0

    monkeypatch.setattr("src.bot.Exchange", lambda: DummyExchange())
    monkeypatch.setattr("src.bot.get_db", lambda: DummyDB())
    monkeypatch.setattr("src.bot.notify.send", lambda msg: calls.append(("notify", msg)))
    monkeypatch.setattr("src.bot.time.sleep", lambda s: None)

    result = run_minimum_trade_smoke_test(symbol="BTCUSDT", wait_seconds=0)

    assert result["sold"] is True
    assert result["symbol"] == "BTCUSDT"
    assert any(call[0] == "sell" for call in calls)


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


def test_init_db_crea_tabla_de_historial_de_operaciones():
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

    assert any("CREATE TABLE IF NOT EXISTS trade_history" in query for query, _ in executed)


def test_executor_registra_compra_fallida_en_market_history(monkeypatch):
    captured = {}

    class DummyDB:
        def record_market_event(self, symbol, interval, signal, price, strategy_name, **kwargs):
            captured["event"] = {
                "symbol": symbol,
                "interval": interval,
                "signal": signal,
                "price": price,
                "strategy_name": strategy_name,
                "note": kwargs.get("note"),
            }
            return captured["event"]

        def upsert_open_position(self, **kwargs):
            return None

    class DummyExchange:
        def get_symbol_filters(self, symbol):
            return {"LOT_SIZE": {"stepSize": 0.000001}}

        def market_buy(self, symbol, quote_amount):
            raise RuntimeError("MIN_NOTIONAL")

    monkeypatch.setattr(executor_module, "get_db", lambda: DummyDB())

    risk = RiskManager(quote_per_trade=1.0, stop_loss_pct=0.02, take_profit_pct=0.04, max_daily_loss=1.0)
    exchange = DummyExchange()
    executor = Executor(exchange, risk)
    executor._open(60000.0)

    assert captured["event"]["signal"] == "BUY"
    assert "MIN_NOTIONAL" in captured["event"]["note"]
