import json
import copy
import ssl
from abc import ABC
from abc import abstractmethod
from typing import Any
from urllib.request import Request
from urllib.request import urlopen

import certifi

from app.ai.reports import ResearchReportOutput
from app.core.config import Settings
from app.core.config import get_settings
from app.core.secrets import SecretManagerResolver


def _normalize_usage(value: Any) -> dict[str, int | bool] | None:
    if not isinstance(value, dict):
        return None
    try:
        input_tokens = int(value.get("input_tokens"))
        output_tokens = int(value.get("output_tokens"))
    except (TypeError, ValueError):
        return None
    if input_tokens < 0 or output_tokens < 0:
        return None
    total_raw = value.get("total_tokens")
    try:
        total_tokens = int(total_raw) if total_raw is not None else input_tokens + output_tokens
    except (TypeError, ValueError):
        return None
    if total_tokens < input_tokens + output_tokens:
        return None
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "provider_reported": True,
    }


def _closed_openai_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Strict Structured Outputs requires closed objects and every property required."""
    result = copy.deepcopy(schema)
    def visit(node):
        if not isinstance(node, dict):
            return
        if node.get("type") == "object":
            if "properties" not in node:
                raise ValueError("open-ended objects must use an explicit wire representation")
            node["additionalProperties"] = False
            node["required"] = list(node["properties"])
        for key, value in node.items():
            if key == "properties" or key == "$defs":
                for child in value.values():
                    visit(child)
            elif key == "items":
                visit(value)
            elif key in {"anyOf", "allOf", "oneOf"}:
                for child in value:
                    visit(child)
    visit(result)
    return result


def _openai_report_schema() -> dict[str, Any]:
    schema = ResearchReportOutput.model_json_schema()
    # Domain reports retain arbitrary fact/evidence dictionaries. JSON-object
    # strings preserve their contents without an unsupported open object on wire.
    for key in ("input_facts", "evidence"):
        schema["properties"][key] = {"type":"string", "description":f"A JSON-encoded object for {key}; use an empty JSON object string if no fields apply."}
    return _closed_openai_schema(schema)


def _decode_openai_report_output(raw: str, canonical_facts: dict[str, Any] | None = None) -> str:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("report must be an object")
    for key in ("input_facts", "evidence"):
        if not isinstance(value.get(key), str):
            raise ValueError("report wire dictionaries must be JSON strings")
        decoded = json.loads(value[key])
        if not isinstance(decoded, dict):
            raise ValueError("report wire dictionary must decode to an object")
        value[key] = decoded
    if canonical_facts is not None:
        value["input_facts"] = canonical_facts
    return ResearchReportOutput.model_validate(value).model_dump_json()


def _tls_context() -> ssl.SSLContext:
    # Use the certifi CA bundle explicitly: on some machines Python's default
    # trust store is incomplete and provider TLS handshakes fail even though
    # certifi (already a project dependency) validates the chain fine.
    return ssl.create_default_context(cafile=certifi.where())


class AIProvider(ABC):
    @abstractmethod
    def generate_report(
        self,
        *,
        report_type: str,
        agent_name: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        raise NotImplementedError


class MockAIProvider(AIProvider):
    def generate_report(
        self,
        *,
        report_type: str,
        agent_name: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        data_available = bool(input_facts)
        fact_keys = sorted(input_facts.keys())
        unavailable_text = "Data unavailable in the provided structured input facts."

        report = {
            "report_id": f"mock-{data_snapshot_id}",
            "report_type": report_type,
            "agent_name": agent_name,
            "data_snapshot_id": data_snapshot_id,
            "input_facts": input_facts,
            "summary": self._summary(report_type, fact_keys) if data_available else unavailable_text,
            "bullish_case": self._case("bullish", fact_keys) if data_available else unavailable_text,
            "bearish_case": self._case("bearish", fact_keys) if data_available else unavailable_text,
            "key_risks": self._risks(input_facts) if data_available else [unavailable_text],
            "suggested_action": "review_only",
            "confidence": 0.7 if data_available else 0.2,
            "evidence": {
                "source": "input_facts",
                "available_fields": fact_keys,
            },
            "limitations": self._limitations(data_available),
        }
        return json.dumps(report)

    def _summary(self, report_type: str, fact_keys: list[str]) -> str:
        return f"Mock {report_type} report based only on structured fields: {', '.join(fact_keys)}."

    def _case(self, direction: str, fact_keys: list[str]) -> str:
        return f"{direction.title()} view is limited to provided fields: {', '.join(fact_keys)}."

    def _risks(self, input_facts: dict[str, Any]) -> list[str]:
        risks = input_facts.get("risks")
        if isinstance(risks, list) and risks:
            return [str(risk) for risk in risks]
        return ["No explicit risk facts were provided; review source data completeness."]

    def _limitations(self, data_available: bool) -> str:
        if not data_available:
            return "Data unavailable; no external facts were inferred."
        return "Mock provider does not call external models and does not infer facts outside input_facts."

    def generate_thesis_capture(
        self,
        *,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        market_context = input_facts.get("market_context") or {}
        current_position = input_facts.get("current_position") or {}
        user_rationale = str(input_facts.get("user_rationale") or "").strip()
        intended_action = str(input_facts.get("intended_action") or "review").strip()

        key_drivers = market_context.get("key_drivers")
        if not isinstance(key_drivers, list) or not key_drivers:
            key_drivers = ["user_stated_rationale"] if user_rationale else []

        invalidation_conditions = market_context.get("invalidation_conditions")
        if not isinstance(invalidation_conditions, list) or not invalidation_conditions:
            invalidation_conditions = [
                "The stated key drivers are no longer supported by new structured facts.",
                "Loss exceeds the configured thesis max loss tolerance.",
            ]

        payload = {
            "entry_reason": user_rationale,
            "key_drivers": [str(driver) for driver in key_drivers],
            "invalidation_conditions": [str(condition) for condition in invalidation_conditions],
            "expected_horizon": str(market_context.get("expected_horizon") or "swing"),
            "target_condition": str(
                market_context.get("target_condition")
                or f"Review before taking action '{intended_action}' if thesis drivers change."
            ),
            "max_loss_tolerance_pct": float(market_context.get("max_loss_tolerance_pct", 0.08)),
            "position_plan": {
                "intended_action": intended_action,
                "current_position": current_position,
                "source": "mock_provider_structured_inputs_only",
            },
            "confidence": float(market_context.get("confidence", 0.7)),
        }
        return json.dumps(payload)

    def generate_thesis_monitor(
        self,
        *,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        has_data = any(
            bool(input_facts.get(key))
            for key in (
                "new_facts",
                "news",
                "price_movement",
                "earnings_data",
                "technical_signals",
                "onchain_signals",
            )
        )
        new_facts = input_facts.get("new_facts") or {}
        price_movement = input_facts.get("price_movement") or {}
        earnings_data = input_facts.get("earnings_data") or {}
        technical_signals = input_facts.get("technical_signals") or []
        thesis = input_facts.get("thesis") or {}

        max_loss_tolerance_pct = float(thesis.get("max_loss_tolerance_pct") or 0)
        drawdown_pct = abs(float(price_movement.get("drawdown_pct") or 0))
        negative_signal = any(str(signal.get("direction", "")).lower() == "bearish" for signal in technical_signals if isinstance(signal, dict))

        if not has_data:
            checkpoint_status = "DATA_INSUFFICIENT"
            summary = "Data insufficient; no thesis validity conclusion was made."
            confidence = 0.0
        elif new_facts.get("invalidation_triggered") or earnings_data.get("missed_key_driver") or (max_loss_tolerance_pct and drawdown_pct >= max_loss_tolerance_pct):
            checkpoint_status = "INVALIDATES_THESIS"
            summary = "Structured facts indicate a thesis invalidation condition may be triggered."
            confidence = 0.8
        elif new_facts.get("weakens_thesis") or negative_signal:
            checkpoint_status = "WEAKENS_THESIS"
            summary = "Structured facts weaken the thesis and require review."
            confidence = 0.65
        elif new_facts.get("supports_thesis") or earnings_data.get("supports_key_driver"):
            checkpoint_status = "SUPPORTS_THESIS"
            summary = "Structured facts support the current thesis."
            confidence = 0.7
        else:
            checkpoint_status = "DATA_INSUFFICIENT"
            summary = "Provided facts do not map clearly to support, weakening, or invalidation."
            confidence = 0.2

        return json.dumps(
            {
                "checkpoint_status": checkpoint_status,
                "observed_facts": input_facts,
                "ai_summary": summary,
                "confidence": confidence,
            }
        )

    def generate_thesis_violation_message(
        self,
        *,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        current_action = str(input_facts.get("current_action") or "User action").strip()
        prior_statement = str(input_facts.get("prior_user_statement") or "Prior thesis").strip()
        return json.dumps(
            {
                "violation_type": "THESIS_CONFLICT",
                "message": f"This action may conflict with your recorded thesis: {current_action}",
                "explanation": f"Prior thesis statement was: {prior_statement}",
                "intervention_level": input_facts.get("intervention_level") or "HARD_CONFIRM",
            }
        )


class OpenAIProvider(AIProvider):
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        secret_resolver: SecretManagerResolver | None = None,
        transport: Any | None = None,
    ):
        self.settings = settings or get_settings()
        self.secret_resolver = secret_resolver or SecretManagerResolver(self.settings)
        self.transport = transport or self._request
        self.last_usage: dict[str, int | bool] | None = None

    def generate_report(
        self,
        *,
        report_type: str,
        agent_name: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        provider_model = f"openai:{self.settings.openai_model}"
        if not self.settings.external_llm_calls_enabled:
            raise ValueError("external LLM calls are disabled")
        if provider_model not in self.settings.llm_provider_allowlist:
            raise ValueError("OpenAI model is not in the configured allowlist")
        if not self.settings.openai_api_key_ref:
            raise ValueError("OPENAI_API_KEY_REF is required")
        api_key = self.secret_resolver.resolve(self.settings.openai_api_key_ref).value
        schema = _openai_report_schema()
        payload = {
            "model": self.settings.openai_model,
            "instructions": (
                "Use only the supplied structured facts. Do not invent external facts. "
                "Return review-only research and never propose broker, exchange, wallet, or execution calls. Serialize input_facts and evidence output fields as JSON-encoded object strings. Set output input_facts to an empty JSON object string; the server restores canonical supplied facts. Preserve the nested evidence contents.\n\n"
                + prompt_template
            ),
            "input": json.dumps(
                {
                    "report_type": report_type,
                    "agent_name": agent_name,
                    "data_snapshot_id": data_snapshot_id,
                    "input_facts": input_facts,
                },
                ensure_ascii=True,
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "research_report",
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        response = self.transport(payload, api_key)
        self.last_usage = _normalize_usage(response.get("usage"))
        output_text = response.get("output_text")
        if not output_text:
            for item in response.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        output_text = content["text"]
                        break
        if not isinstance(output_text, str) or not output_text.strip():
            raise ValueError("OpenAI response did not contain structured output text")
        return _decode_openai_report_output(output_text, input_facts)

    def generate_thesis_capture(self, *, input_facts: dict[str, Any], prompt_template: str) -> str:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "entry_reason": {"type": "string"},
                "key_drivers": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "invalidation_conditions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "expected_horizon": {"type": "string"},
                "target_condition": {"type": "string"},
                "max_loss_tolerance_pct": {"type": "number", "minimum": 0, "maximum": 1},
                "position_plan": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"intended_action": {"type": "string"}, "source": {"type": "string"}},
                    "required": ["intended_action", "source"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["entry_reason", "key_drivers", "invalidation_conditions", "expected_horizon", "target_condition", "max_loss_tolerance_pct", "position_plan", "confidence"],
        }
        return self._structured_output("thesis_capture", schema, input_facts, prompt_template)

    def generate_thesis_monitor(self, *, input_facts: dict[str, Any], prompt_template: str) -> str:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "checkpoint_status": {"type": "string", "enum": ["SUPPORTS_THESIS", "WEAKENS_THESIS", "INVALIDATES_THESIS", "DATA_INSUFFICIENT"]},
                "observed_facts": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"source": {"type": "string"}, "fact_count": {"type": "integer", "minimum": 0}},
                    "required": ["source", "fact_count"],
                },
                "ai_summary": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["checkpoint_status", "observed_facts", "ai_summary", "confidence"],
        }
        return self._structured_output("thesis_monitor", schema, input_facts, prompt_template)

    def generate_thesis_violation_message(self, *, input_facts: dict[str, Any], prompt_template: str) -> str:
        schema = {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "violation_type": {"type": "string"},
                "message": {"type": "string"},
                "explanation": {"type": "string"},
                "intervention_level": {"type": "string", "enum": ["SILENT_RECORD", "SOFT_WARNING", "HARD_CONFIRM", "BLOCK"]},
            },
            "required": ["violation_type", "message", "explanation", "intervention_level"],
        }
        return self._structured_output("thesis_violation_message", schema, input_facts, prompt_template)

    def _structured_output(self, name: str, schema: dict[str, Any], input_facts: dict[str, Any], prompt_template: str) -> str:
        provider_model = f"openai:{self.settings.openai_model}"
        if not self.settings.external_llm_calls_enabled:
            raise ValueError("external LLM calls are disabled")
        if provider_model not in self.settings.llm_provider_allowlist:
            raise ValueError("OpenAI model is not in the configured allowlist")
        if not self.settings.openai_api_key_ref:
            raise ValueError("OPENAI_API_KEY_REF is required")
        api_key = self.secret_resolver.resolve(self.settings.openai_api_key_ref).value
        response = self.transport(
            {
                "model": self.settings.openai_model,
                "instructions": "Use only supplied structured facts. Never call tools, execute trades, or infer missing facts.\n\n" + prompt_template,
                "input": json.dumps(input_facts, ensure_ascii=True),
                "text": {"format": {"type": "json_schema", "name": name, "strict": True, "schema": _closed_openai_schema(schema)}},
            },
            api_key,
        )
        self.last_usage = _normalize_usage(response.get("usage"))
        output_text = response.get("output_text")
        if not output_text:
            for item in response.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text" and content.get("text"):
                        output_text = content["text"]
                        break
        if not isinstance(output_text, str) or not output_text.strip():
            raise ValueError("OpenAI response did not contain structured output text")
        return output_text

    def _request(self, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = Request(
            f"{self.settings.openai_base_url.rstrip('/')}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.external_api_timeout_seconds, context=_tls_context()) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError("OpenAI Responses API request failed") from exc
        if not isinstance(result, dict):
            raise ValueError("OpenAI Responses API returned an invalid response")
        return result


class DeepSeekProvider(AIProvider):
    """Anthropic-Messages-compatible provider (DeepSeek's /anthropic endpoint) using forced tool-use for structured output."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        secret_resolver: SecretManagerResolver | None = None,
        transport: Any | None = None,
    ):
        self.settings = settings or get_settings()
        self.secret_resolver = secret_resolver or SecretManagerResolver(self.settings)
        self.transport = transport or self._request
        self.last_usage: dict[str, int | bool] | None = None

    def generate_report(
        self,
        *,
        report_type: str,
        agent_name: str,
        data_snapshot_id: str,
        input_facts: dict[str, Any],
        prompt_template: str,
    ) -> str:
        schema = ResearchReportOutput.model_json_schema()
        return self._structured_output(
            "emit_research_report",
            schema,
            {
                "report_type": report_type,
                "agent_name": agent_name,
                "data_snapshot_id": data_snapshot_id,
                "input_facts": input_facts,
            },
            "Use only the supplied structured facts. Do not invent external facts. "
            "Return review-only research and never propose broker, exchange, wallet, or execution calls.\n\n"
            + prompt_template,
        )

    def generate_thesis_capture(self, *, input_facts: dict[str, Any], prompt_template: str) -> str:
        schema = {
            "type": "object",
            "properties": {
                "entry_reason": {"type": "string"},
                "key_drivers": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "invalidation_conditions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
                "expected_horizon": {"type": "string"},
                "target_condition": {"type": "string"},
                "max_loss_tolerance_pct": {"type": "number", "minimum": 0, "maximum": 1},
                "position_plan": {
                    "type": "object",
                    "properties": {"intended_action": {"type": "string"}, "source": {"type": "string"}},
                    "required": ["intended_action", "source"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["entry_reason", "key_drivers", "invalidation_conditions", "expected_horizon", "target_condition", "max_loss_tolerance_pct", "position_plan", "confidence"],
        }
        return self._structured_output("emit_thesis_capture", schema, input_facts, prompt_template)

    def generate_thesis_monitor(self, *, input_facts: dict[str, Any], prompt_template: str) -> str:
        schema = {
            "type": "object",
            "properties": {
                "checkpoint_status": {"type": "string", "enum": ["SUPPORTS_THESIS", "WEAKENS_THESIS", "INVALIDATES_THESIS", "DATA_INSUFFICIENT"]},
                "observed_facts": {
                    "type": "object",
                    "properties": {"source": {"type": "string"}, "fact_count": {"type": "integer", "minimum": 0}},
                    "required": ["source", "fact_count"],
                },
                "ai_summary": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["checkpoint_status", "observed_facts", "ai_summary", "confidence"],
        }
        return self._structured_output("emit_thesis_monitor", schema, input_facts, prompt_template)

    def generate_thesis_violation_message(self, *, input_facts: dict[str, Any], prompt_template: str) -> str:
        schema = {
            "type": "object",
            "properties": {
                "violation_type": {"type": "string"},
                "message": {"type": "string"},
                "explanation": {"type": "string"},
                "intervention_level": {"type": "string", "enum": ["SILENT_RECORD", "SOFT_WARNING", "HARD_CONFIRM", "BLOCK"]},
            },
            "required": ["violation_type", "message", "explanation", "intervention_level"],
        }
        return self._structured_output("emit_violation_message", schema, input_facts, prompt_template)

    def _structured_output(self, tool_name: str, schema: dict[str, Any], input_facts: dict[str, Any], prompt_template: str) -> str:
        provider_model = f"deepseek:{self.settings.deepseek_model}"
        if not self.settings.external_llm_calls_enabled:
            raise ValueError("external LLM calls are disabled")
        if provider_model not in self.settings.llm_provider_allowlist:
            raise ValueError("DeepSeek model is not in the configured allowlist")
        if not self.settings.deepseek_api_key_ref:
            raise ValueError("DEEPSEEK_API_KEY_REF is required")
        api_key = self.secret_resolver.resolve(self.settings.deepseek_api_key_ref).value
        response = self.transport(
            {
                "model": self.settings.deepseek_model,
                "max_tokens": 4096,
                "thinking": {"type":"disabled"},
                "system": (
                    "Use only supplied structured facts. Never call tools other than the one provided, "
                    "execute trades, or infer missing facts.\n\n" + prompt_template
                ),
                "messages": [{"role": "user", "content": json.dumps(input_facts, ensure_ascii=True)}],
                "tools": [
                    {
                        "name": tool_name,
                        "description": "Return the structured result for this request.",
                        "input_schema": schema,
                    }
                ],
                "tool_choice": {"type": "tool", "name": tool_name},
            },
            api_key,
        )
        self.last_usage = _normalize_usage(response.get("usage"))
        for block in response.get("content", []):
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                tool_input = block.get("input")
                if not isinstance(tool_input, dict):
                    raise ValueError("DeepSeek response tool_use input was not an object")
                return json.dumps(tool_input, ensure_ascii=True)
        raise ValueError("DeepSeek response did not contain structured tool output")

    def _request(self, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
        request = Request(
            f"{self.settings.deepseek_anthropic_base_url.rstrip('/')}/v1/messages",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.external_api_timeout_seconds, context=_tls_context()) as response:
                result = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ValueError("DeepSeek Anthropic-compatible API request failed") from exc
        if not isinstance(result, dict):
            raise ValueError("DeepSeek Anthropic-compatible API returned an invalid response")
        return result
