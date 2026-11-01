from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from urllib.request import Request
from urllib.request import urlopen

from app.core.config import Settings
from app.core.config import get_settings


class SecretResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class SecretResolution:
    reference: str
    backend: str
    value: str
    version: str | None = None


class SecretManagerResolver:
    """Resolve secret references without persisting or logging secret values."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    def resolve(self, reference: str) -> SecretResolution:
        ref = str(reference or "").strip()
        if not ref or "://" not in ref:
            raise SecretResolutionError("a typed secret reference is required")
        if ref.startswith("env://"):
            return self._env(ref)
        if ref.startswith("aws-sm://"):
            return self._aws(ref)
        if ref.startswith("gcp-sm://"):
            return self._gcp(ref)
        if ref.startswith("vault://"):
            return self._vault(ref)
        raise SecretResolutionError("unsupported secret reference backend")

    def verify(self, reference: str) -> dict[str, Any]:
        result = self.resolve(reference)
        return {
            "reference": result.reference,
            "backend": result.backend,
            "version": result.version,
            "resolved": bool(result.value),
            "contains_secret": False,
        }

    def _env(self, reference: str) -> SecretResolution:
        name = reference.removeprefix("env://").strip()
        if not name or not name.replace("_", "").isalnum():
            raise SecretResolutionError("invalid environment secret reference")
        value = os.getenv(name)
        if not value:
            raise SecretResolutionError(f"environment secret reference is unavailable: {name}")
        return SecretResolution(reference=reference, backend="env", value=value)

    def _aws(self, reference: str) -> SecretResolution:
        secret_spec = reference.removeprefix("aws-sm://")
        secret_id, _, json_key = secret_spec.partition("#")
        if not secret_id:
            raise SecretResolutionError("AWS secret id is required")
        try:
            import boto3  # type: ignore[import-not-found]
        except ImportError as exc:
            raise SecretResolutionError("boto3 is required for aws-sm references") from exc
        response = boto3.client("secretsmanager", region_name=self.settings.aws_region).get_secret_value(SecretId=secret_id)
        value = response.get("SecretString")
        if not value:
            raise SecretResolutionError("AWS secret has no SecretString value")
        if json_key:
            value = str(json.loads(value)[json_key])
        return SecretResolution(reference=reference, backend="aws_secrets_manager", value=value, version=response.get("VersionId"))

    def _gcp(self, reference: str) -> SecretResolution:
        resource = reference.removeprefix("gcp-sm://").strip("/")
        parts = resource.split("/")
        if len(parts) not in {2, 3}:
            raise SecretResolutionError("GCP reference must be gcp-sm://project/secret[/version]")
        project, secret = parts[0], parts[1]
        version = parts[2] if len(parts) == 3 else "latest"
        token_ref = self.settings.gcp_access_token_ref
        if not token_ref:
            raise SecretResolutionError("GCP_ACCESS_TOKEN_REF is required")
        token = self.resolve(token_ref).value
        url = (
            "https://secretmanager.googleapis.com/v1/projects/"
            f"{quote(project)}/secrets/{quote(secret)}/versions/{quote(version)}:access"
        )
        payload = self._json_request(url, headers={"Authorization": f"Bearer {token}"})
        encoded = str((payload.get("payload") or {}).get("data") or "")
        if not encoded:
            raise SecretResolutionError("GCP secret payload is empty")
        import base64

        value = base64.b64decode(encoded).decode("utf-8")
        return SecretResolution(reference=reference, backend="gcp_secret_manager", value=value, version=version)

    def _vault(self, reference: str) -> SecretResolution:
        spec = reference.removeprefix("vault://")
        path, _, field = spec.partition("#")
        if not path or not field:
            raise SecretResolutionError("Vault reference must include path and #field")
        if not self.settings.vault_address or not self.settings.vault_token_ref:
            raise SecretResolutionError("VAULT_ADDRESS and VAULT_TOKEN_REF are required")
        token = self.resolve(self.settings.vault_token_ref).value
        url = f"{self.settings.vault_address.rstrip('/')}/v1/{path.lstrip('/')}"
        payload = self._json_request(url, headers={"X-Vault-Token": token})
        data = payload.get("data") or {}
        if isinstance(data.get("data"), dict):
            data = data["data"]
        value = data.get(field)
        if value in {None, ""}:
            raise SecretResolutionError("Vault secret field is unavailable")
        return SecretResolution(reference=reference, backend="vault", value=str(value), version=str((payload.get("data") or {}).get("metadata", {}).get("version") or "") or None)

    def _json_request(self, url: str, *, headers: dict[str, str]) -> dict[str, Any]:
        request = Request(url, headers={**headers, "Accept": "application/json"}, method="GET")
        try:
            with urlopen(request, timeout=self.settings.external_api_timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise SecretResolutionError("secret manager request failed") from exc
        if not isinstance(payload, dict):
            raise SecretResolutionError("secret manager returned an invalid response")
        return payload
