"""Carga y valida la configuracion desde variables de entorno (.env)."""
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Binance
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_testnet: bool = True

    # Mercado
    symbol: str = "BTCUSDT"
    interval: str = "1h"

    # Riesgo
    quote_per_trade: float = 10.0
    max_open_positions: int = 10
    stop_loss_pct: float = 0.03
    take_profit_pct: float = 0.03
    max_daily_loss: float = 10.0

    # Estrategia
    strategy: str = "sma_cross_rsi"  # ver STRATEGIES en src/strategy.py
    fast_ma: int = 25
    slow_ma: int = 50
    rsi_period: int = 14
    rsi_min: float = 45.0
    rsi_max: float = 70.0
    # solo para strategy = "rsi_reversion"
    rsi_buy: float = 25.0
    rsi_exit: float = 55.0

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Loop
    poll_seconds: int = 60
    dry_run: bool = True

    # PostgreSQL local
    postgres_dsn: str = Field(
        default="",
        validation_alias=AliasChoices("postgres_dsn", "POSTGRES_DSN"),
    )
    postgres_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("postgres_enabled", "POSTGRES_ENABLED"),
    )


settings = Settings()
