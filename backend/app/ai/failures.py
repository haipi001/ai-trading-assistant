"""Public diagnostic categories. Never include request URLs, headers or response bodies."""
import ssl
from app.core.secrets import SecretResolutionError
from urllib.error import HTTPError, URLError


def provider_failure_code(error: Exception) -> str:
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, SecretResolutionError):
            return "credential_unavailable"
        if isinstance(current, HTTPError):
            return {401: "authentication", 402: "billing", 403: "permission", 404: "endpoint_or_model", 429: "rate_limit"}.get(current.code, "provider_unavailable" if current.code >= 500 else "request_rejected")
        if isinstance(current, (TimeoutError,)):
            return "timeout"
        if isinstance(current, ssl.SSLError):
            return "tls"
        if isinstance(current, URLError):
            if isinstance(current.reason, ssl.SSLError):
                return "tls"
            if isinstance(current.reason, TimeoutError):
                return "timeout"
            return "network"
        current = current.__cause__ or current.__context__
    return "unknown"
