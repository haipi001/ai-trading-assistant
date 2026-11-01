from fastapi.testclient import TestClient

from app.services.web3_risk import Web3RiskReadOnlyService


PUBLIC_ADDRESS = "0x1111111111111111111111111111111111111111"
SPENDER_ADDRESS = "0x2222222222222222222222222222222222222222"


def register_wallet(client: TestClient, address: str = PUBLIC_ADDRESS) -> dict:
    response = client.post(
        "/web3/wallets",
        json={
            "user_id": "user-1",
            "address": address,
            "chain": "ethereum",
            "label": "Read-only treasury wallet",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_wallet_can_be_registered_by_public_address(client: TestClient) -> None:
    wallet = register_wallet(client)

    assert wallet["address"] == PUBLIC_ADDRESS
    assert wallet["chain"] == "ethereum"
    assert wallet["is_active"] is True

    list_response = client.get("/web3/wallets?user_id=user-1")
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == wallet["id"]


def test_private_key_like_wallet_input_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/web3/wallets",
        json={
            "user_id": "user-1",
            "address": "private key 0x1111111111111111111111111111111111111111",
            "chain": "ethereum",
            "label": "unsafe input",
        },
    )

    assert response.status_code == 422


def test_allowance_risk_alert_created(client: TestClient) -> None:
    wallet = register_wallet(client)

    response = client.post(
        "/web3/risk-scan",
        json={
            "user_id": "user-1",
            "wallet_id": wallet["id"],
            "allowances": [
                {
                    "token": "USD Coin",
                    "symbol": "USDC",
                    "spender": SPENDER_ADDRESS,
                    "amount": 100_000,
                    "usd_value": 100_000,
                }
            ],
            "max_allowance_usd": 10_000,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["signing_available"] is False
    assert payload["execution_available"] is False
    assert payload["alerts_created"] == 1
    assert payload["alerts"][0]["alert_type"] == "EXCESSIVE_TOKEN_ALLOWANCE"

    allowances = client.get(f"/web3/wallets/{wallet['id']}/allowances").json()
    assert allowances[0]["spender"] == SPENDER_ADDRESS
    assert allowances[0]["risk_level"] == "high"
    summary = client.get("/web3/risk-summary?user_id=user-1").json()
    assert summary["allowances"][0]["riskLevel"] == "high"
    assert summary["signing_available"] is False
    assert summary["execution_available"] is False


def test_stablecoin_exposure_calculated(client: TestClient) -> None:
    wallet = register_wallet(client)

    response = client.post(
        "/web3/risk-scan",
        json={
            "user_id": "user-1",
            "wallet_id": wallet["id"],
            "balances": [
                {
                    "token": "USD Coin",
                    "symbol": "USDC",
                    "balance": 25_000,
                    "usd_price": 0.96,
                    "usd_value": 24_000,
                    "reference_price": 0.96,
                }
            ],
            "stablecoin_depeg_threshold": 0.02,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["stablecoin_exposures"][0]["symbol"] == "USDC"
    assert payload["stablecoin_exposures"][0]["issuer"] == "Circle"
    assert payload["stablecoin_exposures"][0]["depeg_risk_score"] > 0.02
    assert payload["alerts"][0]["alert_type"] == "STABLECOIN_DEPEG_RISK"


def test_exchange_and_transfer_risks_create_alerts(client: TestClient) -> None:
    wallet = register_wallet(client)

    response = client.post(
        "/web3/risk-scan",
        json={
            "user_id": "user-1",
            "wallet_id": wallet["id"],
            "exchange_exposures": [
                {
                    "exchange_name": "ExampleCEX",
                    "asset_symbol": "USDC",
                    "usd_value": 80_000,
                    "exposure_pct": 0.6,
                }
            ],
            "transfers": [
                {
                    "tx_hash": "0xabc",
                    "from_address": PUBLIC_ADDRESS,
                    "to_address": "0x3333333333333333333333333333333333333333",
                    "token": "Ether",
                    "symbol": "ETH",
                    "amount": 40,
                    "usd_value": 120_000,
                    "direction": "outgoing",
                    "is_known_contract": False,
                }
            ],
        },
    )

    assert response.status_code == 201
    alert_types = {alert["alert_type"] for alert in response.json()["alerts"]}
    assert "SINGLE_EXCHANGE_EXPOSURE_TOO_HIGH" in alert_types
    assert "UNKNOWN_CONTRACT_INTERACTION" in alert_types
    assert "LARGE_OUTGOING_TRANSFER" in alert_types
    summary = client.get("/web3/risk-summary?user_id=user-1").json()
    assert summary["exchange"][0]["name"] == "ExampleCEX"
    assert summary["exchange"][0]["allocationPct"] == 60


def test_no_signing_or_dex_execution_interface_exists() -> None:
    forbidden_methods = {
        "sign_transaction",
        "sign_message",
        "build_transaction",
        "send_transaction",
        "execute_swap",
        "dex_swap",
        "place_order",
    }

    assert forbidden_methods.isdisjoint(set(dir(Web3RiskReadOnlyService)))


def test_evm_rpc_adapter_reads_native_and_erc20_balances() -> None:
    from app.adapters.evm_rpc_readonly import EvmRpcReadOnlyAdapter

    calls: list[dict] = []

    def transport(payload):
        calls.append(payload)
        if payload["method"] == "eth_getBalance":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(2 * 10**18)}  # 2 ETH
        if payload["method"] == "eth_call":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(1_500_000)}  # 1.5 USDC (6 decimals)
        raise AssertionError(f"unexpected method {payload['method']}")

    adapter = EvmRpcReadOnlyAdapter(transport=transport)
    assert adapter.get_native_balance(PUBLIC_ADDRESS) == 2.0
    assert adapter.get_erc20_balance("0x3333333333333333333333333333333333333333", PUBLIC_ADDRESS, decimals=6) == 1.5
    assert calls[1]["params"][0]["data"].startswith("0x70a08231")
    assert PUBLIC_ADDRESS[2:].lower() in calls[1]["params"][0]["data"]


def test_evm_rpc_adapter_rejects_bad_input() -> None:
    import pytest

    from app.adapters.evm_rpc_readonly import EvmRpcError, EvmRpcReadOnlyAdapter, validate_evm_address

    with pytest.raises(EvmRpcError):
        validate_evm_address("not-an-address")
    with pytest.raises(EvmRpcError):
        EvmRpcReadOnlyAdapter(rpc_url="http://insecure.example.com")

    def error_transport(payload):
        return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "boom"}}

    adapter = EvmRpcReadOnlyAdapter(transport=error_transport)
    with pytest.raises(EvmRpcError, match="rpc error"):
        adapter.get_native_balance(PUBLIC_ADDRESS)


def test_evm_rpc_adapter_exposes_no_signing_capability() -> None:
    import pytest
    from app.adapters.evm_rpc_readonly import EvmRpcError, EvmRpcReadOnlyAdapter

    forbidden = {"sign_transaction", "sign_message", "send_transaction", "send_raw_transaction", "build_transaction", "execute_swap"}
    assert forbidden.isdisjoint(set(dir(EvmRpcReadOnlyAdapter)))
    adapter = EvmRpcReadOnlyAdapter(transport=lambda payload: {"result": "0x0"})
    with pytest.raises(EvmRpcError, match="outside the read-only allowlist"):
        adapter._call("eth_sendRawTransaction", ["0xdeadbeef"])


def test_wallet_rpc_refresh_persists_real_read_balances(client: TestClient, monkeypatch) -> None:
    from app.adapters import evm_rpc_readonly

    def transport(payload):
        if payload["method"] == "eth_getBalance":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(3 * 10**18)}
        if payload["method"] == "eth_call":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(250 * 10**6)}
        raise AssertionError(payload["method"])

    original_init = evm_rpc_readonly.EvmRpcReadOnlyAdapter.__init__

    def patched_init(self, *, rpc_url=None, timeout_seconds=15, transport_override=transport, **kwargs):
        original_init(self, rpc_url=rpc_url, timeout_seconds=timeout_seconds, transport=transport_override)

    monkeypatch.setattr(evm_rpc_readonly.EvmRpcReadOnlyAdapter, "__init__", patched_init)

    wallet = register_wallet(client)
    response = client.post(
        f"/web3/wallets/{wallet['id']}/rpc-refresh",
        json={"erc20_tokens": [{"address": "0x3333333333333333333333333333333333333333", "symbol": "USDC", "decimals": 6}]},
    )
    assert response.status_code == 201, response.text
    balances = response.json()
    assert len(balances) == 2
    native = next(item for item in balances if item["symbol"] == "ETH")
    usdc = next(item for item in balances if item["symbol"] == "USDC")
    assert float(native["balance"]) == 3.0
    assert float(usdc["balance"]) == 250.0
    assert native["source"] == "evm_rpc_readonly"

    audit_response = client.get("/audit-logs")
    assert any(log["action"] == "web3.wallet.rpc_refreshed" for log in audit_response.json())


def test_wallet_rpc_refresh_reads_allowances_and_flags_unlimited(client: TestClient, monkeypatch) -> None:
    from app.adapters import evm_rpc_readonly

    unlimited = 2**256 - 1

    def transport(payload):
        if payload["method"] == "eth_getBalance":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(10**18)}
        if payload["method"] == "eth_call":
            data = payload["params"][0]["data"]
            if data.startswith("0xdd62ed3e"):
                return {"jsonrpc": "2.0", "id": 1, "result": hex(unlimited)}
            return {"jsonrpc": "2.0", "id": 1, "result": hex(0)}
        raise AssertionError(payload["method"])

    original_init = evm_rpc_readonly.EvmRpcReadOnlyAdapter.__init__

    def patched_init(self, *, rpc_url=None, timeout_seconds=15, transport_override=transport, **kwargs):
        original_init(self, rpc_url=rpc_url, timeout_seconds=timeout_seconds, transport=transport_override)

    monkeypatch.setattr(evm_rpc_readonly.EvmRpcReadOnlyAdapter, "__init__", patched_init)

    wallet = register_wallet(client)
    response = client.post(
        f"/web3/wallets/{wallet['id']}/rpc-refresh",
        json={
            "allowances": [
                {"token_address": "0x3333333333333333333333333333333333333333", "symbol": "USDC", "spender": SPENDER_ADDRESS, "decimals": 6}
            ]
        },
    )
    assert response.status_code == 201, response.text

    allowances = client.get(f"/web3/wallets/{wallet['id']}/allowances").json()
    rpc_rows = [item for item in allowances if item["source"] == "evm_rpc_readonly"]
    assert rpc_rows and rpc_rows[0]["risk_level"] == "high"

    alerts = client.get(f"/web3/wallets/{wallet['id']}/risk-alerts").json()
    assert any(alert["alert_type"] == "UNLIMITED_TOKEN_ALLOWANCE" for alert in alerts)


def test_evm_adapter_for_chain_resolves_known_chains() -> None:
    from app.adapters.evm_rpc_readonly import EvmRpcError, EvmRpcReadOnlyAdapter

    base = EvmRpcReadOnlyAdapter.for_chain("base")
    assert base.expected_chain_id == 8453
    assert base.rpc_url.startswith("https://")
    assert base.native_symbol == "ETH"

    arb = EvmRpcReadOnlyAdapter.for_chain("arbitrum-one")
    assert arb.expected_chain_id == 42161

    polygon = EvmRpcReadOnlyAdapter.for_chain(137)
    assert polygon.expected_chain_id == 137
    assert polygon.native_symbol == "POL"

    import pytest

    with pytest.raises(EvmRpcError):
        EvmRpcReadOnlyAdapter.for_chain("not-a-chain")


def test_verify_chain_is_fail_closed_on_wrong_network() -> None:
    import pytest

    from app.adapters.evm_rpc_readonly import EvmRpcError, EvmRpcReadOnlyAdapter

    # Node reports mainnet (chain_id 1) but we expected Base (8453).
    def wrong_chain_transport(payload):
        if payload["method"] == "eth_chainId":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(1)}
        raise AssertionError(payload["method"])

    adapter = EvmRpcReadOnlyAdapter(transport=wrong_chain_transport, expected_chain_id=8453)
    with pytest.raises(EvmRpcError, match="does not match expected"):
        adapter.verify_chain()

    # Correct network verifies and returns the id.
    def right_chain_transport(payload):
        if payload["method"] == "eth_chainId":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(8453)}
        raise AssertionError(payload["method"])

    ok = EvmRpcReadOnlyAdapter(transport=right_chain_transport, expected_chain_id=8453)
    assert ok.verify_chain() == 8453


def test_rpc_refresh_rejects_unsupported_chain(client: TestClient) -> None:
    # A wallet on a chain with no read-only node in the registry must fail
    # closed rather than silently reading the wrong network.
    response = client.post(
        "/web3/wallets",
        json={"user_id": "user-1", "address": PUBLIC_ADDRESS, "chain": "fantom", "label": "unsupported"},
    )
    assert response.status_code == 201, response.text
    wallet = response.json()
    refresh = client.post(f"/web3/wallets/{wallet['id']}/rpc-refresh", json={})
    assert refresh.status_code == 422
    assert "chain" in refresh.text.lower()


def test_rpc_refresh_attaches_usd_prices_fail_closed(client: TestClient, monkeypatch) -> None:
    # Injectable price provider keeps the test offline: ETH priced, unknown
    # token returns None -> usd_value stays 0 (nothing invented).
    from app.adapters import evm_rpc_readonly
    from app.api import web3 as web3_api

    def transport(payload):
        if payload["method"] == "eth_getBalance":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(2 * 10**18)}  # 2 ETH
        if payload["method"] == "eth_call":
            return {"jsonrpc": "2.0", "id": 1, "result": hex(100 * 10**6)}  # 100 units
        raise AssertionError(payload["method"])

    original_init = evm_rpc_readonly.EvmRpcReadOnlyAdapter.__init__

    def patched_init(self, *, rpc_url=None, timeout_seconds=15, transport_override=transport, **kwargs):
        original_init(self, rpc_url=rpc_url, timeout_seconds=timeout_seconds, transport=transport_override)

    monkeypatch.setattr(evm_rpc_readonly.EvmRpcReadOnlyAdapter, "__init__", patched_init)

    def fake_prices(symbol: str):
        if symbol.upper() == "ETH":
            return 3500.0
        if symbol.upper() == "USDC":
            return 1.0
        return None

    # The API resolves the provider by the name imported into its module.
    monkeypatch.setattr(web3_api, "default_onchain_price_provider", fake_prices)

    wallet = register_wallet(client)
    response = client.post(
        f"/web3/wallets/{wallet['id']}/rpc-refresh",
        json={
            "attach_prices": True,
            "erc20_tokens": [{"address": "0x3333333333333333333333333333333333333333", "symbol": "MYSTERY", "decimals": 6}],
            "allowances": [{"token_address": "0x3333333333333333333333333333333333333333", "symbol": "USDC", "spender": SPENDER_ADDRESS, "decimals": 6}],
            "protocol_positions": [{"token_address": "0x3333333333333333333333333333333333333333", "symbol": "USDC", "protocol_name": "Aave", "position_type": "supplied", "decimals": 6}],
        },
    )
    assert response.status_code == 201, response.text
    balances = {b["symbol"]: b for b in response.json()}
    eth = balances["ETH"]
    assert float(eth["usd_price"]) == 3500.0
    assert float(eth["usd_value"]) == 7000.0  # 2 ETH * 3500
    mystery = balances["MYSTERY"]
    assert float(mystery["usd_price"]) == 0  # unpriced -> not invented
    assert float(mystery["usd_value"]) == 0

    allowances = client.get(f"/web3/wallets/{wallet['id']}/allowances").json()
    assert float(allowances[0]["usd_value"]) == 100.0
    protocols = client.get(f"/web3/wallets/{wallet['id']}/protocol-positions").json()
    assert protocols[0]["protocol_name"] == "Aave"
    assert float(protocols[0]["usd_value"]) == 100.0

    catalog = client.get("/data-catalog/entries?dataset_type=evm_wallet_readonly").json()
    assert catalog and catalog[0]["data_snapshot_id"]
    assert catalog[0]["quality_report_id"]
    assert catalog[0]["contract_json"]["signing_available"] is False
    assert catalog[0]["contract_json"]["transaction_building"] is False

    summary = client.get("/web3/multi-chain-summary?user_id=user-1").json()
    assert summary["chains"][0]["protocols"] == ["Aave"]
    assert summary["total_protocol_exposure_usd"] == 100.0
    assert summary["signing_available"] is False


def test_rpc_refresh_rejects_custom_url_with_embedded_credentials(client: TestClient) -> None:
    wallet = register_wallet(client)
    response = client.post(
        f"/web3/wallets/{wallet['id']}/rpc-refresh",
        json={"rpc_url": "https://user:secret@example.invalid/rpc?api_key=secret"},
    )

    assert response.status_code == 422
    assert "credential-free" in response.json()["detail"]


def test_multi_chain_summary_aggregates_verified_chain_balances(client: TestClient, monkeypatch) -> None:
    from app.adapters import evm_rpc_readonly
    from app.api import web3 as web3_api

    original_init = evm_rpc_readonly.EvmRpcReadOnlyAdapter.__init__

    def patched_init(self, *, rpc_url=None, timeout_seconds=15, expected_chain_id=None, native_symbol=None, **kwargs):
        def transport(payload):
            if payload["method"] == "eth_chainId":
                return {"jsonrpc": "2.0", "id": 1, "result": hex(expected_chain_id)}
            if payload["method"] == "eth_getBalance":
                return {"jsonrpc": "2.0", "id": 1, "result": hex(10**18)}
            raise AssertionError(payload["method"])

        original_init(
            self,
            rpc_url=rpc_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
            expected_chain_id=expected_chain_id,
            native_symbol=native_symbol,
        )

    monkeypatch.setattr(evm_rpc_readonly.EvmRpcReadOnlyAdapter, "__init__", patched_init)
    monkeypatch.setattr(web3_api, "default_onchain_price_provider", lambda symbol: 3000.0 if symbol == "ETH" else None)

    ethereum = register_wallet(client)
    base = client.post(
        "/web3/wallets",
        json={"user_id": "user-1", "address": PUBLIC_ADDRESS, "chain": "base", "label": "Base view-only"},
    ).json()
    assert client.post(f"/web3/wallets/{ethereum['id']}/rpc-refresh", json={}).status_code == 201
    assert client.post(f"/web3/wallets/{base['id']}/rpc-refresh", json={}).status_code == 201

    summary = client.get("/web3/multi-chain-summary?user_id=user-1").json()
    assert {item["chain"] for item in summary["chains"]} == {"ethereum", "base"}
    assert summary["total_balance_usd"] == 6000.0
    assert summary["signing_available"] is False
    assert summary["transaction_building"] is False


def test_onchain_price_provider_pins_stablecoins() -> None:
    from app.services.web3_risk import default_onchain_price_provider

    assert default_onchain_price_provider("USDC") == 1.0
    assert default_onchain_price_provider("DAI") == 1.0
    assert default_onchain_price_provider("") is None
