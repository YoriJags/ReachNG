from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Claude
    anthropic_api_key: str = Field(..., env="ANTHROPIC_API_KEY")

    # Google Maps — internal Prospect OS (SDR funnel) ONLY. Optional: when unset,
    # discovery paths skip Google Maps silently and the app still boots. Never
    # billed to clients, so it must not be a hard startup requirement.
    google_maps_api_key: str | None = Field(default=None, env="GOOGLE_MAPS_API_KEY")

    # Meta Cloud API — WhatsApp Business. Secondary/fallback channel. Unipile is
    # the PRIMARY WhatsApp transport (per-client QR pairing); Meta Cloud is the
    # fallback used where Unipile isn't paired or a client needs an official BSP.
    meta_phone_number_id: str | None = Field(default=None, env="META_PHONE_NUMBER_ID")
    meta_access_token: str | None = Field(default=None, env="META_ACCESS_TOKEN")

    # Resend — transactional email API (HTTPS, no SMTP egress required)
    resend_api_key: str | None = Field(default=None, env="RESEND_API_KEY")
    resend_from_email: str = Field(default="EYO from ReachNG <hello@reachng.ng>", env="RESEND_FROM_EMAIL")
    # Resend webhook signing secret — required to verify email.* events
    resend_webhook_secret: str | None = Field(default=None, env="RESEND_WEBHOOK_SECRET")

    # Gmail SMTP/IMAP — email sending and reply polling (replaces Unipile for email)
    gmail_address: str | None = Field(default=None, env="GMAIL_ADDRESS")
    gmail_app_password: str | None = Field(default=None, env="GMAIL_APP_PASSWORD")
    # Override SMTP host/port for non-Gmail mailboxes (e.g. Go54-hosted hello@reachng.ng).
    # Defaults preserve the existing Gmail SSL behaviour when unset.
    smtp_host: str = Field(default="smtp.gmail.com", env="SMTP_HOST")
    smtp_port: int = Field(default=465, env="SMTP_PORT")
    smtp_use_ssl: bool = Field(default=True, env="SMTP_USE_SSL")
    # IMAP polling for inbound replies. Default points at Gmail; override
    # for Go54 / Zoho / cPanel mailboxes via env (e.g. imap.go54mail.com:993).
    imap_host: str = Field(default="imap.gmail.com", env="IMAP_HOST")
    imap_port: int = Field(default=993, env="IMAP_PORT")

    # Fernet key used to encrypt per-client email passwords at rest (direct
    # IMAP/SMTP connect, no Unipile). When unset, the IMAP email feature refuses
    # to store credentials rather than ever persisting a plaintext password.
    email_cred_key: str | None = Field(default=None, env="EMAIL_CRED_KEY")

    # SDR email cadence: don't email the same business twice within N days,
    # even if it appears in overlapping campaigns. Protects sender reputation
    # and recipient inboxes. Override via env if you need a different window.
    email_cooldown_days: int = Field(default=14, env="EMAIL_COOLDOWN_DAYS")

    # Unipile — PRIMARY transport for the CLIENT EYO ENGINE's WhatsApp. Each
    # client pairs their own number via QR (`whatsapp_account_id` on the client
    # doc); customer replies send from that client's number via /api/v1/chats.
    # Meta Cloud (above) is the optional official/compliant per-client provider.
    #
    # NOT for Yori's internal Prospect OS email — acquisition email goes through
    # Resend (force_smtp), never Unipile. `unipile_whatsapp_account_id` below is
    # only ReachNG's own single-tenant account (last-resort for clients with no
    # connected account). Optional here so the app boots before Unipile is paid.
    unipile_api_key: str | None = Field(default=None, env="UNIPILE_API_KEY")
    unipile_dsn: str | None = Field(default=None, env="UNIPILE_DSN")
    unipile_whatsapp_account_id: str | None = Field(default=None, env="UNIPILE_WHATSAPP_ACCOUNT_ID")
    unipile_email_account_id: str | None = Field(default=None, env="UNIPILE_EMAIL_ACCOUNT_ID")
    unipile_instagram_account_id: str | None = Field(default=None, env="UNIPILE_INSTAGRAM_ACCOUNT_ID")
    unipile_linkedin_account_id: str | None = Field(default=None, env="UNIPILE_LINKEDIN_ACCOUNT_ID")
    # Shared secret Unipile sends back as X-Notify-Token on hosted-auth completion.
    # Optional but recommended in production — if unset, webhook routes by name field only.
    unipile_hosted_notify_token: str | None = Field(default=None, env="UNIPILE_HOSTED_NOTIFY_TOKEN")
    # Optional protection floor: before a Unipile WhatsApp send, verify the number
    # is actually on WhatsApp. Default OFF and fail-open — the Unipile endpoint
    # must be validated before enabling, or it could block legitimate sends.
    whatsapp_existence_check: bool = Field(default=False, env="WHATSAPP_EXISTENCE_CHECK")

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

    # OpenAI — Whisper transcription for inbound voice notes (T0.1)
    openai_api_key: str | None = Field(default=None, env="OPENAI_API_KEY")

    # WhatsApp inbound webhook verify token (Meta handshake) — set WEBHOOK_VERIFY_TOKEN in env
    webhook_verify_token: str | None = Field(default=None, env="WEBHOOK_VERIFY_TOKEN")
    # Webhook HMAC verification secrets — when set, inbound POSTs without a
    # matching signature header are rejected. Leave unset in dev for backwards
    # compatibility; production MUST set both.
    meta_app_secret:         str | None = Field(default=None, env="META_APP_SECRET")
    unipile_webhook_secret:  str | None = Field(default=None, env="UNIPILE_WEBHOOK_SECRET")

    # Scheduler — when false, APScheduler does NOT start. Required for tests
    # and local dev so we don't fire cron jobs against prod data.
    scheduler_enabled: bool = Field(default=True, env="SCHEDULER_ENABLED")

    # PostHog analytics
    posthog_api_key: str | None = Field(default=None, env="POSTHOG_API_KEY")
    posthog_host: str = Field(default="https://us.i.posthog.com", env="POSTHOG_HOST")

    # Sentry error tracking — no-op until SENTRY_DSN is set. PII is scrubbed
    # before send (phone/email) since we never ship customer PII off-box.
    sentry_dsn: str | None = Field(default=None, env="SENTRY_DSN")
    sentry_traces_sample_rate: float = Field(default=0.0, env="SENTRY_TRACES_SAMPLE_RATE")

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


def unipile_enabled() -> bool:
    """True only when both Unipile DSN + API key are present.

    Used to silently no-op Unipile-dependent code paths (WhatsApp pairing,
    health loop, owner-alert WhatsApp pings, inbound media download, client
    morning brief send) when the operator hasn't paid for Unipile yet.

    Email outbound still works via Resend; WhatsApp outbound still works via
    Meta Cloud API if its env vars are set. Only the Unipile-specific paths
    short-circuit.
    """
    s = get_settings()
    return bool(s.unipile_api_key and s.unipile_dsn)
