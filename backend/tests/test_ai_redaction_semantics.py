from app.services.human_control import HumanControlService

def test_redaction_explicitly_labels_value_omission():
    service = HumanControlService.__new__(HumanControlService)
    result = service._redacted_config({"mode": "bring_your_own", "secret_reference": "env://TEST_PROVIDER_KEY"})
    assert result["secret_value_present"] is False
    assert result["secret_value_redacted"] is True
    assert "api_key" not in result
