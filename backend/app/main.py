import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.agents import router as agents_router
from app.api.ai_provider import router as ai_provider_router
from app.api.automation_policy import router as automation_policy_router
from app.api.backtests import router as backtests_router
from app.api.beta import router as beta_router
from app.api.behavior import router as behavior_router
from app.api.broker_connections import router as broker_connections_router
from app.api.exchange_connections import router as exchange_connections_router
from app.api.command_bar import router as command_bar_router
from app.api.complete_product import router as complete_product_router
from app.api.controlled_auto import router as controlled_auto_router
from app.api.daily_use import router as daily_use_router
from app.api.data_catalog import router as data_catalog_router
from app.api.data_sources import pipeline_router as data_pipeline_router
from app.api.data_sources import router as data_sources_router
from app.api.demo import router as demo_router
from app.api.external_data import router as external_data_router
from app.api.domain import router as domain_router
from app.api.imports import router as imports_router
from app.api.ledger import router as ledger_router
from app.api.decision_gates import router as decision_gates_router
from app.api.fundraising import router as fundraising_router
from app.api.health import router as health_router
from app.api.live_execution import kill_switch_router
from app.api.live_execution import router as live_execution_router
from app.api.mock import router as mock_router
from app.api.monthly_reviews import router as monthly_reviews_router
from app.api.modules import router as modules_router
from app.api.ops import router as ops_router
from app.api.paper_execution import router as paper_execution_router
from app.api.phase_development import router as phase_development_router
from app.api.playbook_updates import router as playbook_updates_router
from app.api.portfolio import router as portfolio_router
from app.api.product_roadmap import router as product_roadmap_router
from app.api.production import router as production_router
from app.api.reports import router as reports_router
from app.api.news_feed import router as news_feed_router
from app.api.research_feeds import router as research_feeds_router
from app.api.risk import router as risk_router
from app.api.scheduled_jobs import router as scheduled_jobs_router
from app.api.self_logic import router as self_logic_router
from app.api.signals import router as signals_router
from app.api.strategy_rules import router as strategy_rules_router
from app.api.theses import router as theses_router
from app.api.web3 import router as web3_router
from app.api.workflows import router as workflows_router
from app.core.config import get_settings
from app.core.auth_middleware import ManagedAuthMiddleware
from app.core.local_secrets import load_user_secrets
from app.core.safe_logging import SafeRequestLoggingMiddleware
from app.services.runtime_scheduler import run_runtime_scheduler


def create_app() -> FastAPI:
    load_user_secrets()
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        stop_event = asyncio.Event()
        task = None
        if settings.runtime_scheduler_enabled:
            task = asyncio.create_task(run_runtime_scheduler(stop_event, poll_seconds=settings.runtime_scheduler_poll_seconds))
        try:
            yield
        finally:
            stop_event.set()
            if task is not None:
                await task

    app = FastAPI(
        title="AI Trading OS Backend",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ManagedAuthMiddleware)
    if settings.safe_request_logging_enabled:
        logging.getLogger("uvicorn.access").disabled = True
        app.add_middleware(SafeRequestLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(ai_provider_router)
    app.include_router(demo_router)
    app.include_router(external_data_router)
    app.include_router(domain_router)
    app.include_router(imports_router)
    app.include_router(ledger_router)
    app.include_router(data_sources_router)
    app.include_router(data_pipeline_router)
    app.include_router(data_catalog_router)
    app.include_router(mock_router)
    app.include_router(monthly_reviews_router)
    app.include_router(paper_execution_router)
    app.include_router(playbook_updates_router)
    app.include_router(portfolio_router)
    app.include_router(reports_router)
    app.include_router(research_feeds_router)
    app.include_router(news_feed_router)
    app.include_router(agents_router)
    app.include_router(signals_router)
    app.include_router(risk_router)
    app.include_router(scheduled_jobs_router)
    app.include_router(self_logic_router)
    app.include_router(workflows_router)
    app.include_router(decision_gates_router)
    app.include_router(theses_router)
    app.include_router(behavior_router)
    app.include_router(automation_policy_router)
    app.include_router(strategy_rules_router)
    app.include_router(controlled_auto_router)
    app.include_router(backtests_router)
    app.include_router(modules_router)
    app.include_router(broker_connections_router)
    app.include_router(exchange_connections_router)
    app.include_router(command_bar_router)
    app.include_router(web3_router)
    app.include_router(daily_use_router)
    app.include_router(beta_router)
    app.include_router(ops_router)
    app.include_router(fundraising_router)
    app.include_router(complete_product_router)
    app.include_router(product_roadmap_router)
    app.include_router(production_router)
    app.include_router(phase_development_router)
    app.include_router(live_execution_router)
    app.include_router(kill_switch_router)
    return app


app = create_app()
