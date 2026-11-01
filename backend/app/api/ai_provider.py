from fastapi import APIRouter
from fastapi import Depends

from app.core.config import Settings
from app.core.config import get_settings
from app.schemas import AIProviderStatusRead

router = APIRouter(tags=["ai-provider"])


@router.get("/ai/provider-status", response_model=AIProviderStatusRead)
def ai_provider_status(settings: Settings = Depends(get_settings)) -> AIProviderStatusRead:
    return AIProviderStatusRead(
        default_provider=settings.ai_provider_default,
        external_calls_enabled=settings.external_llm_calls_enabled,
        openai_configured=bool(settings.openai_api_key_ref),
        openai_model=settings.openai_model,
        deepseek_configured=bool(settings.deepseek_api_key_ref),
        deepseek_model=settings.deepseek_model,
        safe_mode="mock_only" if not settings.external_llm_calls_enabled else "external_calls_explicitly_enabled",
        limitations=[
            "LLM providers cannot execute orders or call broker/exchange/wallet adapters.",
            "OpenAI and DeepSeek calls require an exact provider:model allowlist entry and a resolvable secret reference.",
            "AI outputs must use structured input facts and pass evaluator validation before downstream use.",
        ],
    )
