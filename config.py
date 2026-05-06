from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Claude
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")

    # Google Maps
    google_maps_api_key: str = Field(..., env="GOOGLE_MAPS_API_KEY")

    # Meta Cloud API — WhatsApp Business (replaces Unipile for WhatsApp)
    meta_phone_number_id: str | None = Field(default=None, env="META_PHONE_NUMBER_ID")
    meta_access_token: str | None = Field(default=None, env="META_ACCESS_TOKEN")

    # Gmail SMTP/IMAP — email sending and reply polling (replaces Unipile for email)
    gmail_address: str | None = Field(default=None, env="GMAIL_ADDRESS")
    gmail_app_password: str | None = Field(default=None, env="GMAIL_APP_PASSWORD")

    # Unipile — kept optional for clients still using it in agency mode
    unipile_api_key: str | None = Field(default=None, env="UNIPILE_API_KEY")
    unipile_dsn: str | None = Field(default=None, env="UNIPILE_DSN")
    unipile_whatsapp_account_id: str | None = Field(default=None, env="UNIPILE_WHATSAPP_ACCOUNT_ID")
    unipile_email_account_id: str | None = Field(default=None, env="UNIPILE_EMAIL_ACCOUNT_ID")
    unipile_instagram_account_id: str | None = Field(default=None, env="UNIPILE_INSTAGRAM_ACCOUNT_ID")
    unipile_linkedin_account_id: str | None = Field(default=None, env="UNIPILE_LINKEDIN_ACCOUNT_ID")

    # MongoDB
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_db_name: str = Field(default="reachng", env="MONGODB_DB_NAME")

    # Campaign settings
    default_city: str = Field(default="Lagos, Nigeria", env="DEFAULT_CITY")
    daily_send_limit: int = Field(default=50, env="DAILY_SEND_LIMIT")
    followup_delay_hours: int = Field(default=48, env="FOLLOWUP_DELAY_HOURS")
    max_followup_attempts: int = Field(default=2, env="MAX_FOLLOWUP_ATTEMPTS")
    lead_refresh_days: int = Field(default=90, env="LEAD_REFRESH_DAYS")
    city_expand_threshold: float = Field(default=0.4, env="CITY_EXPAND_THRESHOLD")

    # Apollo.io B2B discovery
    apollo_api_key: str | None = Field(default=None, env="APOLLO_API_KEY")

    # Social media discovery
    apify_api_token: str | None = Field(default=None, env="APIFY_API_TOKEN")
    twitter_bearer_token: str | None = Field(default=None, env="TWITTER_BEARER_TOKEN")

    # Facebook Ads Library — long-lived user access token from developers.facebook.com
    # Without this, fb_ads discovery is silently skipped.
    fb_ads_access_token: str | None = Field(default=None, env="FB_ADS_ACCESS_TOKEN")

    # Paystack — Nigerian payment processing (client subscriptions)
    paystack_secret_key: str | None = Field(default=None, env="PAYSTACK_SECRET_KEY")
    paystack_public_key: str | None = Field(default=None, env="PAYSTACK_PUBLIC_KEY")

    # App public URL — used in morning brief portal links
    app_base_url: str = Field(default="https://reachng.up.railway.app", env="APP_BASE_URL")

    # Owner notifications
    owner_whatsapp: str | None = Field(default=None, env="OWNER_WHATSAPP")
    slack_webhook_url: str | None = Field(default=None, env="SLACK_WEBHOOK_URL")

    # Dashboard auth (set both in Railway → never leave blank in production)
    dashboard_user: str | None = Field(default=None, env="DASHBOARD_USER")
    dashboard_pass: str | None = Field(default=None, env="DASHBOARD_PASS")

    # CORS — comma-separated allowed origins. Leave blank to allow all (dev only).
    # Example: https://reachng.co,https://portal.reachng.co
    allowed_origins: str | None = Field(default=None, env="ALLOWED_ORIGINS")

    # Gemini Flash (cheap extraction — PDF parsing, data scraping)
    gemini_api_key: str | None = Field(default=None, env="GEMINI_API_KEY")

    # WhatsApp inbound webhook verify token (Meta handshake) — set WEBHOOK_VERIFY_TOKEN in env
    webhook_verify_token: str | None = Field(default=None, env="WEBHOOK_VERIFY_TOKEN")

    # PostHog analytics
    posthog_api_key: str | None = Field(default=None, env="POSTHOG_API_KEY")
    posthog_host: str = Field(default="https://us.i.posthog.com", env="POSTHOG_HOST")

    # App
    app_env: str = Field(default="development", env="APP_ENV")
    app_port: int = Field(default=8000, env="PORT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
