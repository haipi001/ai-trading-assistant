from urllib.error import HTTPError, URLError
import ssl
from app.ai.failures import provider_failure_code


def test_nested_http_failures_are_classified_without_sensitive_content():
    error = ValueError("wrapper")
    error.__cause__ = HTTPError("https://secret.example/key", 401, "private body", {}, None)
    assert provider_failure_code(error) == "authentication"
    assert provider_failure_code(HTTPError("private", 429, "private", {}, None)) == "rate_limit"


def test_transport_categories_and_unknown_are_safe():
    assert provider_failure_code(URLError(ssl.SSLError("private"))) == "tls"
    assert provider_failure_code(TimeoutError("private")) == "timeout"
    assert provider_failure_code(URLError("private")) == "network"
    assert provider_failure_code(ValueError("secret")) == "unknown"


def test_credential_resolution_failure_is_distinct_from_network():
    from app.core.secrets import SecretResolutionError
    assert provider_failure_code(SecretResolutionError("private reference")) == "credential_unavailable"
