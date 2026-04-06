from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Claude
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")

    # Google Maps
    google_maps_api_key: str = Field(..., env="GOOGLE_MAPS_API_KEY")

    # Unipile
    unipile_api_key: str = Field(..., env="UNIPILE_API_KEY")
    unipile_dsn: str = Field(..., env="UNIPILE_DSN")
    unipile_whatsapp_account_id: str = Field(..., env="UNIPILE_WHATSAPP_ACCOUNT_ID")
    unipile_email_account_id: str = Field(..., env="UNIPILE_EMAIL_ACCOUNT_ID")

    # MongoDB
    mongodb_uri: str = Field(..., env="MONGODB_URI")
    mongodb_db_name: str = Field(default="reachng", env="MONGODB_DB_NAME")

    # Campaign settings
    default_city: str = Field(default="Lagos, Nigeria", env="DEFAULT_CITY")
    daily_send_limit: int = Field(default=50, env="DAILY_SEND_LIMIT")
    followup_delay_hours: int = Field(default=48, env="FOLLOWUP_DELAY_HOURS")
    max_followup_attempts: int = Field(default=2, env="MAX_FOLLOWUP_ATTEMPTS")

    # Apollo.io B2B discovery
    apollo_api_key: str | None = Field(default=None, env="APOLLO_API_KEY")

    # Social media discovery
    apify_api_token: str | None = Field(default=None, env="APIFY_API_TOKEN")
    twitter_bearer_token: str | None = Field(default=None, env="TWITTER_BEARER_TOKEN")

    # Owner notifications
    owner_whatsapp: str | None = Field(default=None, env="OWNER_WHATSAPP")
    slack_webhook_url: str | None = Field(default=None, env="SLACK_WEBHOOK_URL")

    # Dashboard auth (set both in Railway → never leave blank in production)
    dashboard_user: str | None = Field(default=None, env="DASHBOARD_USER")
    dashboard_pass: str | None = Field(default=None, env="DASHBOARD_PASS")

    # CORS — comma-separated allowed origins. Leave blank to allow all (dev only).
    # Example: https://reachng.co,https://portal.reachng.co
    allowed_origins: str | None = Field(default=None, env="ALLOWED_ORIGINS")

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
