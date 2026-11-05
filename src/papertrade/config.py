from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="PT_", extra="ignore", populate_by_name=True)
    mode: Literal["paper"] = "paper"
    execution: Literal["simulator", "brokers"] = "simulator"
    database_url: str = "sqlite:///var/papertrade.db"
    state_dir: Path = Path("var")
    models_dir: Path = Path("var/models")
    capital: float = Field(10000, gt=0)
    risk_per_trade: float = Field(0.005, gt=0, le=0.005)
    daily_loss_limit: float = Field(0.02, gt=0, le=0.02)
    max_drawdown: float = Field(0.10, gt=0, le=0.25)
    max_positions: int = Field(3, ge=1, le=3)
    max_total_exposure: float = Field(0.60, gt=0, le=1)
    max_instrument_exposure: float = Field(0.20, gt=0, le=1)
    max_correlated_exposure: float = Field(0.30, gt=0, le=1)
    max_data_age_seconds: int = Field(1200, ge=900, le=1800)
    max_quote_age_seconds: int = Field(60, gt=0, le=120)
    model_max_age_days: int = Field(30, ge=1, le=90)
    min_probability: float = Field(0.60, ge=0.5, lt=1)
    min_net_edge_bps: float = Field(5, ge=0)
    min_validation_trades: int = Field(30, ge=5)
    allow_unhosted_protection: bool = False
    watchdog_url: SecretStr = SecretStr("")
    alpaca_key: SecretStr = SecretStr("")
    alpaca_secret: SecretStr = SecretStr("")
    oanda_token: SecretStr = SecretStr("")
    oanda_account_id: SecretStr = SecretStr("")
    admin_username: str = "admin"
    admin_password_hash: SecretStr = SecretStr("")
    api_token: SecretStr = SecretStr("")
    api_url: str = "http://127.0.0.1:8000"
    dashboard_refresh_seconds: int = Field(30, ge=5)
    run_paper_integration: bool = False
    # AI is analysis only until its strategy is independently validated and enabled.
    ai_enabled: bool = Field(False, validation_alias=AliasChoices("PT_AI_ENABLED", "AI_ENABLED"))
    ai_provider: Literal["groq", "hermes", "none"] = Field("groq", validation_alias=AliasChoices("PT_AI_PROVIDER", "AI_PROVIDER"))
    ai_fallback_provider: Literal["none"] = Field("none", validation_alias=AliasChoices("PT_AI_FALLBACK_PROVIDER", "AI_FALLBACK_PROVIDER"))
    groq_api_key: SecretStr = Field(SecretStr(""), validation_alias=AliasChoices("PT_GROQ_API_KEY", "GROQ_API_KEY"))
    groq_model: str = Field("", max_length=200, validation_alias=AliasChoices("PT_GROQ_MODEL", "GROQ_MODEL"))
    hermes_api_key: SecretStr = Field(SecretStr(""), validation_alias=AliasChoices("PT_HERMES_API_KEY", "HERMES_API_KEY"))
    hermes_model: str = Field("", max_length=200, validation_alias=AliasChoices("PT_HERMES_MODEL", "HERMES_MODEL"))
    hermes_base_url: str = Field("https://inference-api.nousresearch.com/v1", validation_alias=AliasChoices("PT_HERMES_BASE_URL", "HERMES_BASE_URL"))
    ai_account_tier: Literal["unverified", "free", "paid"] = "unverified"
    ai_allow_paid: bool = False
    ai_timeout_seconds: float = Field(8, ge=1, le=20)
    ai_max_attempts: int = Field(2, ge=1, le=3)
    ai_max_output_tokens: int = Field(512, ge=128, le=2048)
    ai_response_format: Literal["json_object", "json_schema"] = "json_object"
    trading_interval_minutes: int = Field(15, ge=15, le=15, validation_alias=AliasChoices("PT_TRADING_INTERVAL_MINUTES", "TRADING_INTERVAL_MINUTES"))
    ai_analysis_interval_minutes: int = Field(60, ge=15, le=1440, validation_alias=AliasChoices("PT_AI_ANALYSIS_INTERVAL_MINUTES", "AI_ANALYSIS_INTERVAL_MINUTES"))
    ai_max_daily_requests: int = Field(100, ge=0, le=10000, validation_alias=AliasChoices("PT_AI_MAX_DAILY_REQUESTS", "AI_MAX_DAILY_REQUESTS"))
    ai_max_daily_tokens: int = Field(100000, ge=0, le=10000000, validation_alias=AliasChoices("PT_AI_MAX_DAILY_TOKENS", "AI_MAX_DAILY_TOKENS"))
    ai_max_age_minutes: int = Field(75, ge=15, le=75)
    ai_recent_candles: int = Field(12, ge=4, le=24)
    ai_event_probability_delta: float = Field(0.10, gt=0, le=1)
    ai_event_price_change: float = Field(0.02, gt=0, le=0.1)
    ai_event_min_interval_minutes: int = Field(15, ge=15, le=60)
    strategy: Literal["quant_only", "ai_filtered_quant", "hybrid", "ai_only_research"] = "quant_only"
    strategy_execution_enabled: bool = False
    strategy_min_validation_trades: int = Field(30, ge=5)
    strategy_min_observations: int = Field(96, ge=20)
    strategy_certificate_max_age_days: int = Field(30, ge=1, le=90)
    deployment_environment: Literal["local", "oracle", "other"] = "local"

    @model_validator(mode="after")
    def local_storage(self):
        if not self.database_url.startswith("sqlite:///"):
            raise ValueError("This release supports local SQLite storage only")
        return self
