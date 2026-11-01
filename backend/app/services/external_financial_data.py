from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import datetime
from datetime import timezone
from typing import Callable
from urllib.parse import quote
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.request import Request

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.market_data_readonly import open_readonly_url
from app.api.domain import write_audit_log
from app.core.config import Settings
from app.core.config import get_settings
from app.core.secrets import SecretManagerResolver
from app.models import DataCatalogEntry
from app.models import DataQualityReport
from app.models import DataSnapshot
from app.models import ExportArtifact
from app.schemas.core import looks_like_inline_secret_reference
from app.services.ledger import InvestmentLedgerService


class ExternalFinancialDataError(ValueError):
    pass


FetchText = Callable[[str, dict[str, str], float], str]


class ExternalFinancialDataService:
    ECB_HOST = "data-api.ecb.europa.eu"
    NASDAQ_HOST = "api.nasdaq.com"

    def __init__(self, db: Session, *, settings: Settings | None = None, fetch_text: FetchText | None = None):
        self.db = db
        self.settings = settings or get_settings()
        self.fetch_text = fetch_text or self._fetch_text
        self.custom_fetch = fetch_text
        self.secret_resolver = SecretManagerResolver(self.settings)

    def sync_ecb_fx(self, *, currencies: list[str] | None = None) -> dict:
        requested = [item.upper().strip() for item in (currencies or ["USD", "CNY", "HKD", "JPY", "GBP", "CHF"]) if item.strip()]
        requested = list(dict.fromkeys(item for item in requested if re.fullmatch(r"[A-Z]{3}", item)))
        if "USD" not in requested:
            requested.append("USD")
        if not requested:
            raise ExternalFinancialDataError("at least one ISO currency is required")
        series = "+".join(quote(item) for item in requested)
        url = f"https://{self.ECB_HOST}/service/data/EXR/D.{series}.EUR.SP00.A?format=csvdata&lastNObservations=1"
        body = self.fetch_text(url, {"Accept": "text/csv", "User-Agent": "ai-trading-os-readonly/0.1"}, float(self.settings.external_api_timeout_seconds))
        rows = list(csv.DictReader(io.StringIO(body)))
        latest = {}
        for row in rows:
            currency = str(row.get("CURRENCY") or "").upper()
            value = row.get("OBS_VALUE")
            if currency and value not in {None, ""}:
                latest[currency] = {"per_eur": float(value), "date": row.get("TIME_PERIOD"), "status": row.get("OBS_STATUS")}
        if "USD" not in latest:
            raise ExternalFinancialDataError("ECB response did not contain USD reference rate")
        usd_per_eur = latest["USD"]["per_eur"]
        rates = {"EUR": {"to_usd": usd_per_eur, "date": latest["USD"]["date"]}, "USD": {"to_usd": 1.0, "date": latest["USD"]["date"]}}
        for currency, item in latest.items():
            rates[currency] = {"to_usd": usd_per_eur / item["per_eur"], "date": item["date"], "status": item["status"]}
        evidence = self._persist_dataset(
            dataset_type="fx_rates",
            source="ecb_reference_rates",
            source_ref=f"https://{self.ECB_HOST}/service/data/EXR",
            data={"base_currency": "USD", "rates": rates, "provider": "European Central Bank"},
            row_count=len(rates),
            contract={"schema": "ecb_fx_to_usd_v1", "official_source": True, "read_only": True},
        )
        return {"provider": "European Central Bank", "rates": rates, **evidence, "execution_available": False}

    def sync_nasdaq_dividends(self, *, symbols: list[str], limit_per_symbol: int = 20) -> dict:
        normalized = list(dict.fromkeys(item.upper().strip() for item in symbols if re.fullmatch(r"[A-Za-z0-9.\-]{1,16}", item.strip())))
        if not normalized:
            raise ExternalFinancialDataError("at least one valid symbol is required")
        events = []
        errors = []
        for symbol in normalized:
            url = f"https://{self.NASDAQ_HOST}/api/quote/{quote(symbol)}/dividends?assetclass=stocks"
            try:
                body = self.fetch_text(url, {"Accept": "application/json", "User-Agent": "Mozilla/5.0 ai-trading-os-readonly/0.1"}, float(self.settings.external_api_timeout_seconds))
                payload = json.loads(body)
                rows = (((payload.get("data") or {}).get("dividends") or {}).get("rows") or [])[: max(1, min(limit_per_symbol, 100))]
                for row in rows:
                    amount_text = str(row.get("amount") or "").replace("$", "").replace(",", "").strip()
                    events.append({
                        "symbol": symbol,
                        "action_type": "cash_dividend",
                        "ex_date": row.get("exOrEffDate"),
                        "declaration_date": row.get("declarationDate"),
                        "record_date": row.get("recordDate"),
                        "payment_date": row.get("paymentDate"),
                        "amount_per_share": float(amount_text) if amount_text else None,
                        "currency": row.get("currency") or "USD",
                    })
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)})
        if not events:
            raise ExternalFinancialDataError("no corporate action events were returned")
        evidence = self._persist_dataset(
            dataset_type="corporate_actions",
            source="nasdaq_public_dividends",
            source_ref=f"https://{self.NASDAQ_HOST}/api/quote",
            data={"events": events, "errors": errors, "provider": "Nasdaq public endpoint"},
            row_count=len(events),
            contract={"schema": "cash_dividend_event_v1", "read_only": True, "requires_reconciliation_before_promotion": True},
            quality_score=len(events) / max(len(events) + len(errors), 1),
        )
        return {"provider": "Nasdaq public endpoint", "events": events, "errors": errors, **evidence, "execution_available": False}

    def download_statement(
        self,
        *,
        user_id: str,
        url: str,
        provider: str,
        account_label: str | None,
        statement_type: str,
        default_currency: str,
        credentials_ref: str | None = None,
    ) -> dict:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or not host:
            raise ExternalFinancialDataError("statement URL must use HTTPS")
        if host not in self.settings.statement_download_allowed_hosts:
            raise ExternalFinancialDataError("statement host is not in STATEMENT_DOWNLOAD_ALLOWED_HOSTS_RAW")
        if parsed.username or parsed.password:
            raise ExternalFinancialDataError("statement URL must not contain credentials")
        headers = {"Accept": "text/csv", "User-Agent": "ai-trading-os-readonly/0.1"}
        if credentials_ref:
            secret = self.secret_resolver.resolve(credentials_ref).value
            try:
                secret_payload = json.loads(secret)
            except json.JSONDecodeError:
                secret_payload = {"authorization": f"Bearer {secret}"}
            secret_headers = secret_payload.get("headers") if isinstance(secret_payload, dict) else None
            if isinstance(secret_headers, dict):
                for key, value in secret_headers.items():
                    if "\n" in str(key) or "\n" in str(value):
                        raise ExternalFinancialDataError("invalid statement authentication header")
                    if str(key).lower() not in {"authorization", "x-api-key", "x-auth-token", "cookie"}:
                        raise ExternalFinancialDataError("statement secret contains a disallowed header")
                    headers[str(key)] = str(value)
            elif isinstance(secret_payload, dict) and secret_payload.get("authorization"):
                headers["Authorization"] = str(secret_payload["authorization"])
        body = (
            self.custom_fetch(url, headers, float(self.settings.external_api_timeout_seconds))
            if self.custom_fetch is not None
            else self._fetch_statement_text(url, headers, float(self.settings.external_api_timeout_seconds), allowed_host=host)
        )
        if len(body.encode("utf-8")) > 10_000_000:
            raise ExternalFinancialDataError("statement response exceeds 10 MB")
        source_ref = f"https://{host}{parsed.path}"
        result = InvestmentLedgerService(self.db).import_statement(
            user_id=user_id,
            provider=provider,
            account_label=account_label,
            statement_type=statement_type,
            source_ref=source_ref,
            default_currency=default_currency,
            csv_text=body,
        )
        result["download"] = {"host": host, "path": parsed.path, "authenticated": bool(credentials_ref), "credentials_ref": "redacted" if credentials_ref else None}
        return result

    def statement_download_preflight(
        self,
        *,
        url: str,
        credentials_ref: str | None = None,
        verify_secret: bool = False,
    ) -> dict:
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        path = parsed.path or "/"
        blockers: list[str] = []
        warnings: list[str] = []
        next_actions: list[str] = []

        if not url.strip():
            blockers.append("statement_url_required")
            next_actions.append("Paste the HTTPS broker/CEX statement CSV export URL.")
        elif parsed.scheme != "https" or not host:
            blockers.append("statement_url_must_use_https")
            next_actions.append("Use an HTTPS URL without embedded credentials.")
        if parsed.username or parsed.password:
            blockers.append("statement_url_must_not_contain_credentials")
            next_actions.append("Move credentials into a Secret Reference instead of the URL.")
        if host and host not in self.settings.statement_download_allowed_hosts:
            blockers.append("statement_host_not_allowlisted")
            next_actions.append("Add the host to STATEMENT_DOWNLOAD_ALLOWED_HOSTS_RAW before downloading.")

        secret_backend = None
        if credentials_ref:
            ref = credentials_ref.strip()
            if looks_like_inline_secret_reference(ref):
                blockers.append("credentials_ref_looks_like_inline_secret")
                next_actions.append("Use env://, vault://, aws-sm://, or gcp-sm:// instead of pasting a token.")
            elif "://" not in ref:
                blockers.append("typed_secret_reference_required")
                next_actions.append("Use a typed Secret Reference such as env://BROKER_STATEMENT_AUTH.")
            elif verify_secret:
                try:
                    verified = self.secret_resolver.verify(ref)
                    secret_backend = verified.get("backend")
                    if not verified.get("resolved"):
                        blockers.append("secret_reference_not_resolved")
                except Exception as exc:
                    blockers.append("secret_reference_not_resolved")
                    warnings.append(str(exc))
        else:
            warnings.append("statement_download_will_run_without_auth_headers")

        if not blockers:
            next_actions.append("Run safe download and inspect the quality report before ledger promotion.")

        return {
            "status": "ready" if not blockers else "blocked",
            "host": host or None,
            "path": path,
            "allowlisted": bool(host and host in self.settings.statement_download_allowed_hosts),
            "credentials_ref": "redacted" if credentials_ref else None,
            "secret_backend": secret_backend,
            "verify_secret": verify_secret,
            "blockers": blockers,
            "warnings": warnings,
            "next_actions": list(dict.fromkeys(next_actions)),
            "execution_available": False,
            "download_will_not_execute": True,
        }

    def auxiliary_data_status(self, *, user_id: str = "default-user") -> dict:
        statement_hosts = sorted(set(self.settings.statement_download_allowed_hosts))
        items = [
            self._catalog_status_item(
                key="fx_rates",
                label="FX 汇率证据",
                dataset_types=["fx_rates"],
                missing_detail="还没有同步 ECB 官方 FX 汇率；多币种现金和收益折算会停留在预检状态。",
                ready_detail="ECB 官方 FX 汇率已经保存为只读 snapshot 和 quality report。",
                action_label="同步 ECB 汇率",
                route="/?module=settings&tab=data&focus=market_auxiliary",
            ),
            self._catalog_status_item(
                key="corporate_actions",
                label="公司行动证据",
                dataset_types=["corporate_actions"],
                missing_detail="还没有同步公开股息/公司行动；账本对账暂不能自动解释分红类现金流。",
                ready_detail="公开公司行动已经保存为只读 snapshot 和 quality report。",
                action_label="同步公司行动",
                route="/?module=settings&tab=data&focus=market_auxiliary",
            ),
            {
                "key": "statement_download_policy",
                "label": "Statement 下载策略",
                "status": "ready" if statement_hosts else "action_required",
                "detail": "HTTPS allowlist 已配置；下载仍需预检和 Secret Reference。" if statement_hosts else "还没有配置 Statement 下载 allowlist；只能手动导入 CSV。",
                "action_label": "检查下载配置",
                "route": "/?module=settings&tab=data&focus=statement_download",
                "source": "statement_download_policy",
                "snapshot_id": None,
                "quality_report_id": None,
                "catalog_entry_id": None,
                "quality_status": "POLICY_READY" if statement_hosts else "POLICY_REQUIRED",
                "row_count": 0,
                "created_at": None,
                "evidence": {
                    "allowed_hosts_count": len(statement_hosts),
                    "allowlist_configured": bool(statement_hosts),
                    "inline_credentials_allowed": False,
                    "credentials_ref_required_for_auth": True,
                },
            },
            self._catalog_status_item(
                key="statement_import_evidence",
                label="Statement 导入证据",
                dataset_types=["broker_statement", "cex_statement", "wallet_statement", "bank_statement"],
                missing_detail="还没有导入或下载任何 statement；账本对账还缺真实流水证据。",
                ready_detail="Statement 已导入并生成 snapshot、quality report 和 review-only 账本。",
                action_label="导入 Statement",
                route="/?module=settings&tab=data&setup=csv",
            ),
        ]
        ready_count = sum(1 for item in items if item["status"] == "ready")
        missing = [item["key"] for item in items if item["status"] != "ready"]
        first_missing = next((item for item in items if item["status"] != "ready"), None)
        local_next_steps = auxiliary_local_next_steps(items)
        promotion_gate = auxiliary_promotion_gate(items=items, missing=missing)
        return {
            "user_id": user_id,
            "status": "ready_for_local_review" if not missing else "action_required",
            "ready_count": ready_count,
            "total_count": len(items),
            "missing": missing,
            "items": items,
            "local_next_steps": local_next_steps,
            "promotion_gate": promotion_gate,
            "statement_download_policy": {
                "allowlist_configured": bool(statement_hosts),
                "allowed_hosts_count": len(statement_hosts),
                "inline_credentials_allowed": False,
                "credentials_ref_required_for_auth": True,
            },
            "next_action": first_missing["action_label"] if first_missing else "生成辅助数据证据包并回到 Today Queue",
            "safe_boundary": "只读辅助数据状态，不会下单、签名、提现、自动审批或绕过 gates。",
            "execution_available": False,
            "production_capability": False,
        }

    def auxiliary_data_evidence_packet(self, *, user_id: str = "default-user") -> dict:
        generated_at = datetime.now(timezone.utc)
        status = self.auxiliary_data_status(user_id=user_id)
        packet = {
            "packet_type": "market_auxiliary_data_evidence_packet",
            "user_id": user_id,
            "generated_at": generated_at.isoformat(),
            **status,
            "contains_secrets": False,
            "production_capability": False,
            "execution_available": False,
            "safe_boundaries": [
                "read_only_auxiliary_data_only",
                "no_order_submission",
                "no_wallet_signing",
                "no_withdrawal",
                "no_auto_approval",
                "no_gate_bypass",
                "preflight_or_review_only_not_production_capability",
            ],
        }
        artifact = ExportArtifact(
            user_id=user_id,
            export_type="market_auxiliary_data_evidence_packet",
            format="json",
            status=packet["status"],
            payload_json=packet,
            summary_json={
                "ready_count": packet["ready_count"],
                "total_count": packet["total_count"],
                "missing": packet["missing"],
                "contains_secrets": False,
                "production_capability": False,
            },
        )
        self.db.add(artifact)
        self.db.flush()
        packet["artifact_id"] = artifact.id
        write_audit_log(
            self.db,
            action="external_financial_data.auxiliary_evidence_packet_created",
            entity_type="ExportArtifact",
            entity_id=artifact.id,
            payload_json={"ready_count": packet["ready_count"], "total_count": packet["total_count"], "missing": packet["missing"], "execution_available": False},
            actor_id="external-financial-data-service",
        )
        self.db.commit()
        return packet

    def _catalog_status_item(
        self,
        *,
        key: str,
        label: str,
        dataset_types: list[str],
        missing_detail: str,
        ready_detail: str,
        action_label: str,
        route: str,
    ) -> dict:
        catalog = self._latest_catalog(dataset_types)
        if catalog is None:
            return {
                "key": key,
                "label": label,
                "status": "action_required",
                "detail": missing_detail,
                "action_label": action_label,
                "route": route,
                "source": None,
                "snapshot_id": None,
                "quality_report_id": None,
                "catalog_entry_id": None,
                "quality_status": "MISSING",
                "row_count": 0,
                "created_at": None,
                "evidence": {},
            }
        quality = self.db.get(DataQualityReport, catalog.quality_report_id) if catalog.quality_report_id else None
        return {
            "key": key,
            "label": label,
            "status": "ready",
            "detail": ready_detail,
            "action_label": "查看证据",
            "route": route,
            "source": catalog.source,
            "snapshot_id": catalog.data_snapshot_id,
            "quality_report_id": catalog.quality_report_id,
            "catalog_entry_id": catalog.id,
            "quality_status": catalog.quality_status,
            "row_count": catalog.row_count,
            "created_at": catalog.created_at.isoformat() if catalog.created_at else None,
            "evidence": {
                "dataset_type": catalog.dataset_type,
                "source_ref": catalog.source_ref,
                "quality_score": float(quality.score) if quality and quality.score is not None else None,
                "usable_for_trading": bool(catalog.usable_for_trading),
                "review_only": not bool(catalog.usable_for_trading),
            },
        }

    def _latest_catalog(self, dataset_types: list[str]) -> DataCatalogEntry | None:
        return self.db.scalar(
            select(DataCatalogEntry)
            .where(DataCatalogEntry.dataset_type.in_(dataset_types))
            .order_by(DataCatalogEntry.created_at.desc(), DataCatalogEntry.id.desc())
            .limit(1)
        )

    def _persist_dataset(self, *, dataset_type: str, source: str, source_ref: str, data: dict, row_count: int, contract: dict, quality_score: float = 1.0) -> dict:
        fetched_at = datetime.now(timezone.utc)
        content_hash = hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
        snapshot = DataSnapshot(snapshot_type=dataset_type, data_json=data, metadata_json={"provider": source, "source_ref": source_ref, "content_hash": content_hash, "fetched_at": fetched_at.isoformat(), "read_only": True, "execution_available": False})
        self.db.add(snapshot)
        self.db.flush()
        quality = DataQualityReport(data_snapshot_id=snapshot.id, source=source, metric_type=f"{dataset_type}_quality", score=quality_score, details_json={"rows_received": row_count, "source_reachable": True, "content_hash": content_hash, "execution_available": False})
        self.db.add(quality)
        self.db.flush()
        catalog = DataCatalogEntry(dataset_type=dataset_type, source=source, source_ref=source_ref, data_snapshot_id=snapshot.id, quality_report_id=quality.id, row_count=row_count, quality_status="VALID" if quality_score >= 0.8 else "PARTIAL", usable_for_trading=False, lineage_json={"fetched_at": fetched_at.isoformat(), "content_hash": content_hash, "read_only": True}, contract_json={**contract, "execution_available": False})
        self.db.add(catalog)
        self.db.flush()
        write_audit_log(self.db, action="external_financial_data.synced", entity_type="DataSnapshot", entity_id=snapshot.id, payload_json={"dataset_type": dataset_type, "source": source, "row_count": row_count, "content_hash": content_hash, "execution_available": False}, actor_id="external-financial-data-service")
        self.db.commit()
        return {"snapshot_id": snapshot.id, "quality_report_id": quality.id, "catalog_entry_id": catalog.id, "quality_status": catalog.quality_status, "content_hash": content_hash}

    @staticmethod
    def _fetch_text(url: str, headers: dict[str, str], timeout: float) -> str:
        request = Request(url, headers=headers, method="GET")
        try:
            with open_readonly_url(request, timeout=timeout) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            raise ExternalFinancialDataError("external read-only data request failed") from exc

    @staticmethod
    def _fetch_statement_text(url: str, headers: dict[str, str], timeout: float, *, allowed_host: str) -> str:
        request = Request(url, headers=headers, method="GET")
        try:
            with open_readonly_url(request, timeout=timeout) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or (final.hostname or "").lower() != allowed_host:
                    raise ExternalFinancialDataError("statement redirect left the allowlisted HTTPS host")
                return response.read().decode("utf-8", errors="replace")
        except ExternalFinancialDataError:
            raise
        except Exception as exc:
            raise ExternalFinancialDataError("statement read-only download failed") from exc


def auxiliary_local_next_steps(items: list[dict]) -> list[dict]:
    by_key = {item["key"]: item for item in items}
    definitions = [
        {
            "key": "fx_rates",
            "label": "同步 FX 汇率",
            "detail": "多币种现金、收益和风险预算都需要先折算到 USD。",
            "action_label": "同步 ECB 汇率",
            "route": "/?module=settings&tab=data&focus=market_auxiliary",
        },
        {
            "key": "corporate_actions",
            "label": "同步公司行动",
            "detail": "分红、拆股等事件会解释 statement 中的现金流和数量变化。",
            "action_label": "同步公司行动",
            "route": "/?module=settings&tab=data&focus=market_auxiliary",
        },
        {
            "key": "statement_import_evidence",
            "label": "导入或下载 Statement",
            "detail": "Statement 会进入 review-only snapshot、quality report 和账本修复流程。",
            "action_label": "导入 Statement",
            "route": "/?module=settings&tab=data&focus=statement_download",
        },
        {
            "key": "evidence_packet",
            "label": "生成证据包",
            "detail": "把 FX、公司行动、下载策略和导入证据打包，供人工复查。",
            "action_label": "下载证据包",
            "route": "/?module=settings&tab=data&focus=market_auxiliary",
        },
    ]
    steps = []
    all_ready = all((by_key.get(key) or {}).get("status") == "ready" for key in ["fx_rates", "corporate_actions", "statement_import_evidence"])
    for definition in definitions:
        key = definition["key"]
        source = by_key.get(key)
        if key == "evidence_packet":
            status = "ready" if all_ready else "blocked"
            detail = definition["detail"] if all_ready else "先补齐 FX、公司行动和 Statement 证据，再生成完整证据包。"
        else:
            status = "ready" if source and source.get("status") == "ready" else "action_required"
            detail = source.get("detail") if source else definition["detail"]
        steps.append({**definition, "status": status, "detail": detail, "execution_available": False})
    return steps


def auxiliary_promotion_gate(*, items: list[dict], missing: list[str]) -> dict:
    by_key = {item["key"]: item for item in items}
    required = ["fx_rates", "corporate_actions", "statement_import_evidence"]
    ready_required = [key for key in required if (by_key.get(key) or {}).get("status") == "ready"]
    can_review_ledger = "statement_import_evidence" not in missing
    can_use_for_thesis = all(key not in missing for key in ["fx_rates", "corporate_actions"])
    return {
        "status": "ready_for_review" if len(ready_required) == len(required) else "blocked",
        "ready_required": ready_required,
        "missing_required": [key for key in required if key not in ready_required],
        "can_review_ledger": can_review_ledger,
        "can_use_for_thesis_context": can_use_for_thesis,
        "can_unlock_order_approval": False,
        "detail": (
            "辅助数据证据齐全，可以进入人工账本复查、Thesis 上下文和风险解释；仍不能解锁订单审批。"
            if len(ready_required) == len(required)
            else "辅助数据仍缺证据，只能停留在预检和 review-only 状态。"
        ),
        "next_action": "打开账本修复或回 Today Queue" if len(ready_required) == len(required) else "补齐缺失辅助数据证据",
        "execution_available": False,
    }
