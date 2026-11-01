from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic import field_validator
from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict

# Anchor .env to the backend directory: a relative env_file silently resolves
# against the launcher's cwd, so a server started from elsewhere would skip
# .env entirely and fall back to defaults (e.g. the Postgres DATABASE_URL).
_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    environment: str = "local"
    service_name: str = "ai-trading-os-backend"
    release_id: str = "local-development"
    live_trading_enabled: bool = False
    live_execution_enabled: bool = False
    live_execution_dry_run_only: bool = True
    live_execution_adapter_mode: str = "disabled"
    automation_level: str = "A0_READ_ONLY"
    database_url: str = "postgresql+psycopg://ai_trading_os:ai_trading_os@localhost:5432/ai_trading_os"
    redis_url: str = "redis://localhost:6379/0"
    api_rate_limit_enabled: bool = False
    api_rate_limit_requests: int = 120
    api_rate_limit_window_seconds: int = 60
    api_login_rate_limit_requests: int = 10
    api_auth_failure_rate_limit_requests: int = 30
    backend_cors_origins_raw: str = Field(
        default="https://haipi001.github.io,http://localhost:3002,http://127.0.0.1:3002",
        alias="BACKEND_CORS_ORIGINS",
    )
    dependency_check_timeout_seconds: int = 1
    ai_provider_default: str = "mock"
    external_llm_calls_enabled: bool = False
    openai_api_key_ref: str | None = None
    openai_model: str = "gpt-4.1-mini"
    llm_provider_allowlist_raw: str = "openai:gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    deepseek_api_key_ref: str | None = None
    deepseek_model: str = "deepseek-flash"
    deepseek_anthropic_base_url: str = "https://api.deepseek.com/anthropic"
    ai_pricing_version: str | None = None
    openai_input_cost_per_million_usd: float | None = None
    openai_output_cost_per_million_usd: float | None = None
    deepseek_input_cost_per_million_usd: float | None = None
    deepseek_output_cost_per_million_usd: float | None = None
    external_api_timeout_seconds: int = 30
    managed_auth_required: bool = False
    managed_auth_invitation_required: bool = False
    oidc_issuer: str | None = None
    oidc_userinfo_url: str | None = None
    oidc_client_id: str | None = None
    oidc_role_claim: str = "role"
    auth_session_secret_ref: str | None = None
    auth_session_ttl_seconds: int = 3600
    invitation_ttl_hours: int = 72
    invitation_max_attempts: int = 5
    vault_address: str | None = None
    vault_token_ref: str | None = None
    aws_region: str | None = None
    gcp_access_token_ref: str | None = None
    slo_availability_target: float = 0.995
    slo_error_rate_target: float = 0.01
    sandbox_broker_base_url: str | None = None
    sandbox_broker_token_ref: str | None = None
    beta_auth_required: bool = False
    beta_access_token_sha256: str | None = None
    beta_default_user_id: str = "default-user"
    beta_default_role: str = "owner"
    deployment_target: str = "local"
    error_reporting_enabled: bool = False
    safe_request_logging_enabled: bool = True
    observability_metrics_enabled: bool = False
    observability_minimum_requests: int = 100
    staging_fault_injection_enabled: bool = False
    slo_average_latency_ms_target: float = 1000.0
    external_notification_delivery_enabled: bool = False
    notification_webhook_allowed_hosts_raw: str = Field(default="", alias="NOTIFICATION_WEBHOOK_ALLOWED_HOSTS")
    notification_delivery_timeout_seconds: int = 10
    notification_delivery_max_attempts: int = 3
    notification_delivery_retry_seconds: int = 300
    runtime_scheduler_enabled: bool = True
    runtime_scheduler_poll_seconds: int = 30
    statement_download_allowed_hosts_raw: str = ""
    sec_user_agent: str = "ai-trading-os/0.1 local-readonly"

    @field_validator(
        "openai_input_cost_per_million_usd",
        "openai_output_cost_per_million_usd",
        "deepseek_input_cost_per_million_usd",
        "deepseek_output_cost_per_million_usd",
        mode="before",
    )
    @classmethod
    def blank_optional_rate_is_none(cls, value):
        return None if value == "" else value

    @property
    def backend_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins_raw.split(",") if origin.strip()]

    @property
    def llm_provider_allowlist(self) -> list[str]:
        return [item.strip() for item in self.llm_provider_allowlist_raw.split(",") if item.strip()]

    @property
    def statement_download_allowed_hosts(self) -> list[str]:
        return [item.strip().lower() for item in self.statement_download_allowed_hosts_raw.split(",") if item.strip()]

    @property
    def notification_webhook_allowed_hosts(self) -> list[str]:
        return [item.strip().lower() for item in self.notification_webhook_allowed_hosts_raw.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
