from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Иначе `.env` ищется от cwd процесса — при запуске не из корня проекта ключи (TONAPI и др.) не подхватываются.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DOTENV_PATH = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_DOTENV_PATH,
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bot_token: str = Field(alias="BOT_TOKEN")

    @field_validator("bot_token", mode="before")
    @classmethod
    def _strip_bot_token(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip().strip('"').strip("'")
        return v
    database_url: str = Field(alias="DATABASE_URL")
    check_interval_minutes: int = Field(default=10, alias="CHECK_INTERVAL_MINUTES")
    alert_cooldown_minutes: int = Field(default=60, alias="ALERT_COOLDOWN_MINUTES")
    default_marketplace_fee_percent: float = Field(default=5.0, alias="DEFAULT_MARKETPLACE_FEE_PERCENT")
    estimated_extra_costs_ton: float = Field(default=0.0, alias="ESTIMATED_EXTRA_COSTS_TON")
    min_profit_ton: float = Field(default=5.0, alias="MIN_PROFIT_TON")
    default_currency: str = Field(default="TON", alias="DEFAULT_CURRENCY")
    default_risk_mode: str = Field(default="normal", alias="DEFAULT_RISK_MODE")
    enable_mock_source: bool = Field(default=False, alias="ENABLE_MOCK_SOURCE")
    getgems_enabled: bool = Field(default=True, alias="GETGEMS_ENABLED")
    tonapi_enabled: bool = Field(default=True, alias="TONAPI_ENABLED")
    tonnel_enabled: bool = Field(default=True, alias="TONNEL_ENABLED")
    fragment_enabled: bool = Field(default=True, alias="FRAGMENT_ENABLED")
    getgems_base_url: str = Field(default="", alias="GETGEMS_BASE_URL")
    tonapi_base_url: str = Field(default="https://tonapi.io", alias="TONAPI_BASE_URL")
    tonapi_global_rps_limit: float = Field(default=1.0, alias="TONAPI_GLOBAL_RPS_LIMIT")
    tonapi_global_min_interval_ms: int = Field(default=1200, alias="TONAPI_GLOBAL_MIN_INTERVAL_MS")
    ipfs_gateway_url: str = Field(default="https://ipfs.io/ipfs/", alias="IPFS_GATEWAY_URL")
    nft_global_index_enabled: bool = Field(default=False, alias="NFT_GLOBAL_INDEX_ENABLED")
    nft_global_index_provider: str = Field(default="tonapi", alias="NFT_GLOBAL_INDEX_PROVIDER")
    nft_global_index_limit_per_page: int = Field(default=1000, alias="NFT_GLOBAL_INDEX_LIMIT_PER_PAGE")
    nft_global_index_request_sleep_ms: int = Field(default=300, alias="NFT_GLOBAL_INDEX_REQUEST_SLEEP_MS")
    nft_global_index_429_backoff_seconds: float = Field(default=5.0, alias="NFT_GLOBAL_INDEX_429_BACKOFF_SECONDS")
    nft_global_index_max_collections_per_run: int = Field(default=0, alias="NFT_GLOBAL_INDEX_MAX_COLLECTIONS_PER_RUN")
    nft_global_index_sample_items: int = Field(default=20, alias="NFT_GLOBAL_INDEX_SAMPLE_ITEMS")
    nft_global_index_full_items_enabled: bool = Field(default=False, alias="NFT_GLOBAL_INDEX_FULL_ITEMS_ENABLED")
    nft_global_index_live_discovery_for_paid: bool = Field(
        default=True, alias="NFT_GLOBAL_INDEX_LIVE_DISCOVERY_FOR_PAID"
    )
    nft_live_discovery_page_limit: int = Field(default=100, alias="NFT_LIVE_DISCOVERY_PAGE_LIMIT")
    nft_live_discovery_max_pages_free: int = Field(default=2, alias="NFT_LIVE_DISCOVERY_MAX_PAGES_FREE")
    nft_live_discovery_max_pages_paid: int = Field(default=30, alias="NFT_LIVE_DISCOVERY_MAX_PAGES_PAID")
    nft_live_discovery_sleep_ms: int = Field(default=1200, alias="NFT_LIVE_DISCOVERY_SLEEP_MS")
    nft_live_discovery_429_backoff_seconds: int = Field(default=10, alias="NFT_LIVE_DISCOVERY_429_BACKOFF_SECONDS")
    nft_live_discovery_stop_on_429: bool = Field(default=True, alias="NFT_LIVE_DISCOVERY_STOP_ON_429")
    toncenter_api_base_url: str = Field(default="https://toncenter.com", alias="TONCENTER_API_BASE_URL")
    toncenter_enabled: bool = Field(default=False, alias="TONCENTER_ENABLED")
    toncenter_api_key: str = Field(default="", alias="TONCENTER_API_KEY")
    toncenter_timeout_seconds: int = Field(default=15, alias="TONCENTER_TIMEOUT_SECONDS")
    nft_global_resolver_use_toncenter: bool = Field(default=True, alias="NFT_GLOBAL_RESOLVER_USE_TONCENTER")
    nft_global_index_live_discovery_limit: int = Field(default=1000, alias="NFT_GLOBAL_INDEX_LIVE_DISCOVERY_LIMIT")
    nft_global_index_live_discovery_max_pages_free: int = Field(
        default=2, alias="NFT_GLOBAL_INDEX_LIVE_DISCOVERY_MAX_PAGES_FREE"
    )
    nft_global_index_live_discovery_max_pages_paid: int = Field(
        default=30, alias="NFT_GLOBAL_INDEX_LIVE_DISCOVERY_MAX_PAGES_PAID"
    )
    tonnel_base_url: str = Field(default="", alias="TONNEL_BASE_URL")
    fragment_base_url: str = Field(default="", alias="FRAGMENT_BASE_URL")
    getgems_api_key: str = Field(default="", alias="GETGEMS_API_KEY")
    tonapi_api_key: str = Field(default="", alias="TONAPI_API_KEY")
    tonnel_api_key: str = Field(default="", alias="TONNEL_API_KEY")
    fragment_api_key: str = Field(default="", alias="FRAGMENT_API_KEY")
    market_http_timeout_seconds: int = Field(default=10, alias="MARKET_HTTP_TIMEOUT_SECONDS")
    market_http_retries: int = Field(default=2, alias="MARKET_HTTP_RETRIES")
    market_http_user_agent: str = Field(default="GiftSniperBot/1.0", alias="MARKET_HTTP_USER_AGENT")
    collection_registry_path: str = Field(default="data/collections.json", alias="COLLECTION_REGISTRY_PATH")
    fresh_floor_max_minutes: int = Field(default=60, alias="FRESH_FLOOR_MAX_MINUTES")
    stale_floor_max_minutes: int = Field(default=720, alias="STALE_FLOOR_MAX_MINUTES")
    old_floor_max_minutes: int = Field(default=1440, alias="OLD_FLOOR_MAX_MINUTES")
    recent_sales_max_days: int = Field(default=7, alias="RECENT_SALES_MAX_DAYS")
    smart_alert_default_cooldown_minutes: int = Field(default=180, alias="SMART_ALERT_DEFAULT_COOLDOWN_MINUTES")
    smart_alert_strength_drop_threshold: int = Field(default=20, alias="SMART_ALERT_STRENGTH_DROP_THRESHOLD")
    smart_alert_liquidity_crash_threshold: int = Field(default=30, alias="SMART_ALERT_LIQUIDITY_CRASH_THRESHOLD")
    smart_alert_data_stale_minutes: int = Field(default=720, alias="SMART_ALERT_DATA_STALE_MINUTES")
    admin_telegram_ids: str = Field(default="", alias="ADMIN_TELEGRAM_IDS")
    rate_limit_commands_per_minute: int = Field(default=20, alias="RATE_LIMIT_COMMANDS_PER_MINUTE")
    rate_limit_heavy_commands_per_hour: int = Field(default=30, alias="RATE_LIMIT_HEAVY_COMMANDS_PER_HOUR")
    production_mode: bool = Field(default=False, alias="PRODUCTION_MODE")
    allow_mock_in_production: bool = Field(default=False, alias="ALLOW_MOCK_IN_PRODUCTION")
    mock_allowed_for_dev: bool = Field(default=True, alias="MOCK_ALLOWED_FOR_DEV")
    require_real_or_manual_for_trading: bool = Field(default=True, alias="REQUIRE_REAL_OR_MANUAL_FOR_TRADING")
    min_real_market_confidence_for_buy: int = Field(default=45, alias="MIN_REAL_MARKET_CONFIDENCE_FOR_BUY")
    min_real_sales_for_strong_buy: int = Field(default=3, alias="MIN_REAL_SALES_FOR_STRONG_BUY")
    block_trading_verdict_on_mock: bool = Field(default=True, alias="BLOCK_TRADING_VERDICT_ON_MOCK")
    manual_market_enabled: bool = Field(default=True, alias="MANUAL_MARKET_ENABLED")
    billing_enabled: bool = Field(default=False, alias="BILLING_ENABLED")
    billing_grace_period_days: int = Field(default=3, alias="BILLING_GRACE_PERIOD_DAYS")
    billing_default_currency: str = Field(default="USD", alias="BILLING_DEFAULT_CURRENCY")
    billing_provider: str = Field(default="manual", alias="BILLING_PROVIDER")
    public_bot_username: str = Field(default="", alias="PUBLIC_BOT_USERNAME")
    public_bot_access: bool = Field(default=False, alias="PUBLIC_BOT_ACCESS")
    billing_webhooks_enabled: bool = Field(default=False, alias="BILLING_WEBHOOKS_ENABLED")
    mock_billing_enabled: bool = Field(default=False, alias="MOCK_BILLING_ENABLED")
    mock_billing_webhook_secret: str = Field(default="", alias="MOCK_BILLING_WEBHOOK_SECRET")
    billing_webhook_max_attempts: int = Field(default=3, alias="BILLING_WEBHOOK_MAX_ATTEMPTS")
    owner_crypto_wallet_ton: str = Field(
        default="UQBE72wYg608Yc6SfddpPI-_3A0f8Gv9Ap3zjr5f7xu5yec8", alias="OWNER_CRYPTO_WALLET_TON"
    )
    owner_crypto_wallet_usdt: str = Field(default="", alias="OWNER_CRYPTO_WALLET_USDT")
    manual_payment_enabled: bool = Field(default=True, alias="MANUAL_PAYMENT_ENABLED")
    manual_payment_default_currency: str = Field(default="TON", alias="MANUAL_PAYMENT_DEFAULT_CURRENCY")
    manual_payment_confirmation_required: bool = Field(default=True, alias="MANUAL_PAYMENT_CONFIRMATION_REQUIRED")
    manual_payment_starter_ton: float = Field(default=10.0, alias="MANUAL_PAYMENT_STARTER_TON")
    manual_payment_pro_ton: float = Field(default=25.0, alias="MANUAL_PAYMENT_PRO_TON")
    manual_payment_trader_ton: float = Field(default=60.0, alias="MANUAL_PAYMENT_TRADER_TON")
    manual_payment_default_days: int = Field(default=30, alias="MANUAL_PAYMENT_DEFAULT_DAYS")
    manual_payment_request_ttl_hours: int = Field(default=24, alias="MANUAL_PAYMENT_REQUEST_TTL_HOURS")
    manual_payment_submitted_sla_hours: int = Field(default=6, alias="MANUAL_PAYMENT_SUBMITTED_SLA_HOURS")
    admin_payment_alert_cooldown_minutes: int = Field(default=180, alias="ADMIN_PAYMENT_ALERT_COOLDOWN_MINUTES")
    owner_weekly_summary_enabled: bool = Field(default=False, alias="OWNER_WEEKLY_SUMMARY_ENABLED")
    owner_weekly_summary_day: str = Field(default="MON", alias="OWNER_WEEKLY_SUMMARY_DAY")
    owner_weekly_summary_hour: int = Field(default=10, alias="OWNER_WEEKLY_SUMMARY_HOUR")
    owner_accuracy_digest_enabled: bool = Field(default=False, alias="OWNER_ACCURACY_DIGEST_ENABLED")
    owner_accuracy_digest_day: str = Field(default="SUN", alias="OWNER_ACCURACY_DIGEST_DAY")
    owner_accuracy_digest_hour: int = Field(default=18, alias="OWNER_ACCURACY_DIGEST_HOUR")
    beta_mode: bool = Field(default=True, alias="BETA_MODE")
    beta_max_users: int = Field(default=50, alias="BETA_MAX_USERS")
    beta_require_invite: bool = Field(default=True, alias="BETA_REQUIRE_INVITE")
    beta_support_username: str = Field(default="@deliverrrrrr", alias="BETA_SUPPORT_USERNAME")
    beta_feedback_reminder_command_threshold: int = Field(default=5, alias="BETA_FEEDBACK_REMINDER_COMMAND_THRESHOLD")
    important_trait_keywords: str = Field(
        default="monochrome,gold,diamond,legendary,mythic,rare,limited,black,white,silver,platinum",
        alias="IMPORTANT_TRAIT_KEYWORDS",
    )
    pricing_target_roi_conservative: float = Field(default=25.0, alias="PRICING_TARGET_ROI_CONSERVATIVE")
    pricing_target_roi_normal: float = Field(default=18.0, alias="PRICING_TARGET_ROI_NORMAL")
    pricing_target_roi_aggressive: float = Field(default=12.0, alias="PRICING_TARGET_ROI_AGGRESSIVE")
    pricing_no_sales_safe_buy_discount: float = Field(default=0.78, alias="PRICING_NO_SALES_SAFE_BUY_DISCOUNT")
    pricing_low_confidence_discount: float = Field(default=0.90, alias="PRICING_LOW_CONFIDENCE_DISCOUNT")
    pricing_stale_data_discount: float = Field(default=0.92, alias="PRICING_STALE_DATA_DISCOUNT")
    pricing_rare_no_sales_max_tier: str = Field(default="B_TIER", alias="PRICING_RARE_NO_SALES_MAX_TIER")
    pricing_strong_buy_min_confidence: int = Field(default=70, alias="PRICING_STRONG_BUY_MIN_CONFIDENCE")
    pricing_strong_buy_min_liquidity: int = Field(default=60, alias="PRICING_STRONG_BUY_MIN_LIQUIDITY")
    pricing_strong_buy_require_recent_sales: bool = Field(default=True, alias="PRICING_STRONG_BUY_REQUIRE_RECENT_SALES")
    capital_multiplier_min_sale_probability: int = Field(default=45, alias="CAPITAL_MULTIPLIER_MIN_SALE_PROBABILITY")
    capital_multiplier_min_confidence: int = Field(default=45, alias="CAPITAL_MULTIPLIER_MIN_CONFIDENCE")
    capital_multiplier_max_risk: int = Field(default=80, alias="CAPITAL_MULTIPLIER_MAX_RISK")
    capital_multiplier_speculative_max_percent: float = Field(
        default=15.0, alias="CAPITAL_MULTIPLIER_SPECULATIVE_MAX_PERCENT"
    )
    capital_multiplier_top_n: int = Field(default=5, alias="CAPITAL_MULTIPLIER_TOP_N")
    capital_multiplier_signal_snapshots_top_n: int = Field(
        default=3, alias="CAPITAL_MULTIPLIER_SIGNAL_SNAPSHOTS_TOP_N"
    )
    compound_plan_conservative_roi: float = Field(default=15.0, alias="COMPOUND_PLAN_CONSERVATIVE_ROI")
    compound_plan_normal_roi: float = Field(default=25.0, alias="COMPOUND_PLAN_NORMAL_ROI")
    compound_plan_aggressive_roi: float = Field(default=40.0, alias="COMPOUND_PLAN_AGGRESSIVE_ROI")
    full_market_scan_enabled: bool = Field(default=True, alias="FULL_MARKET_SCAN_ENABLED")
    full_market_max_items: int = Field(default=300_000, alias="FULL_MARKET_MAX_ITEMS")
    full_market_page_limit: int = Field(default=10_000, alias="FULL_MARKET_PAGE_LIMIT")
    full_market_page_limit_max: int = Field(default=10_000, alias="FULL_MARKET_PAGE_LIMIT_MAX")
    full_market_page_limit_fallbacks: str = Field(
        default="10000,5000,2000,1000,500,200,100",
        alias="FULL_MARKET_PAGE_LIMIT_FALLBACKS",
    )
    full_market_min_page_limit: int = Field(default=100, alias="FULL_MARKET_MIN_PAGE_LIMIT")
    full_market_scan_mode: str = Field(default="full", alias="FULL_MARKET_SCAN_MODE")
    full_market_full_scan_enabled: bool = Field(default=True, alias="FULL_MARKET_FULL_SCAN_ENABLED")
    full_market_full_scan_max_items: int = Field(default=0, alias="FULL_MARKET_FULL_SCAN_MAX_ITEMS")
    full_market_cache_ttl_seconds: int = Field(default=900, alias="FULL_MARKET_CACHE_TTL_SECONDS")
    full_market_request_sleep_ms: int = Field(default=1200, alias="FULL_MARKET_REQUEST_SLEEP_MS")
    full_market_429_streak_before_reduce_limit: int = Field(default=3, alias="FULL_MARKET_429_STREAK_BEFORE_REDUCE_LIMIT")
    full_market_progress_every_items: int = Field(default=500, alias="FULL_MARKET_PROGRESS_EVERY_ITEMS")
    full_market_min_listings_for_medium_confidence: int = Field(
        default=20, alias="FULL_MARKET_MIN_LISTINGS_FOR_MEDIUM_CONFIDENCE"
    )
    full_market_min_trait_comps_for_confident_price: int = Field(
        default=3, alias="FULL_MARKET_MIN_TRAIT_COMPS_FOR_CONFIDENT_PRICE"
    )
    full_market_http_timeout_seconds: int = Field(default=45, alias="FULL_MARKET_HTTP_TIMEOUT_SECONDS")
    full_market_rate_limit_sleep_seconds: float = Field(default=4.0, alias="FULL_MARKET_RATE_LIMIT_SLEEP_SECONDS")
    full_market_max_429_retries: int = Field(default=8, alias="FULL_MARKET_MAX_429_RETRIES")

    ton_payment_receiver_address: str = Field(default="", alias="TON_PAYMENT_RECEIVER_ADDRESS")
    ton_payment_enabled: bool = Field(default=False, alias="TON_PAYMENT_ENABLED")
    ton_payment_invoice_ttl_minutes: int = Field(default=30, alias="TON_PAYMENT_INVOICE_TTL_MINUTES")
    plan_free_daily_nft_checks: int = Field(default=3, alias="PLAN_FREE_DAILY_NFT_CHECKS")
    plan_free_watchlist_limit: int = Field(default=3, alias="PLAN_FREE_WATCHLIST_LIMIT")
    plan_pro_price_ton: float = Field(default=2.0, alias="PLAN_PRO_PRICE_TON")
    plan_pro_daily_nft_checks: int = Field(default=100, alias="PLAN_PRO_DAILY_NFT_CHECKS")
    plan_pro_watchlist_limit: int = Field(default=50, alias="PLAN_PRO_WATCHLIST_LIMIT")
    plan_sniper_price_ton: float = Field(default=7.0, alias="PLAN_SNIPER_PRICE_TON")
    plan_sniper_daily_nft_checks: int = Field(default=1000, alias="PLAN_SNIPER_DAILY_NFT_CHECKS")
    plan_sniper_watchlist_limit: int = Field(default=300, alias="PLAN_SNIPER_WATCHLIST_LIMIT")
    plan_pro_duration_days: int = Field(default=30, alias="PLAN_PRO_DURATION_DAYS")
    plan_sniper_duration_days: int = Field(default=30, alias="PLAN_SNIPER_DURATION_DAYS")

    signals_enabled: bool = Field(default=True, alias="SIGNALS_ENABLED")
    signals_max_items_per_run: int = Field(default=20, alias="SIGNALS_MAX_ITEMS_PER_RUN")
    signals_request_sleep_ms: int = Field(default=1200, alias="SIGNALS_REQUEST_SLEEP_MS")
    signals_pro_interval_minutes: int = Field(default=360, alias="SIGNALS_PRO_INTERVAL_MINUTES")
    signals_sniper_interval_minutes: int = Field(default=60, alias="SIGNALS_SNIPER_INTERVAL_MINUTES")
    signals_pro_threshold_percent: float = Field(default=20.0, alias="SIGNALS_PRO_THRESHOLD_PERCENT")
    signals_sniper_threshold_percent: float = Field(default=10.0, alias="SIGNALS_SNIPER_THRESHOLD_PERCENT")
    signals_min_hours_between_notifications: int = Field(default=6, alias="SIGNALS_MIN_HOURS_BETWEEN_NOTIFICATIONS")
    signals_min_confidence_collection_market: int = Field(default=55, alias="SIGNALS_MIN_CONFIDENCE_COLLECTION_MARKET")


@lru_cache(1)
def get_settings() -> Settings:
    return Settings()
