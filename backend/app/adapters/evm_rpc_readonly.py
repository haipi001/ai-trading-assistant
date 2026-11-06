"""Read-only EVM JSON-RPC adapter.

Real on-chain reads for registered public wallet addresses: native balance via
`eth_getBalance` and ERC-20 balances via `eth_call` on `balanceOf`. The
adapter exposes no signing, transaction-building, or state-changing method of
any kind — it can only ask a node questions about public state.
"""

from __future__ import annotations

import json
import re
import ssl
from decimal import Decimal, localcontext
from typing import Any
from urllib.request import Request
from urllib.request import urlopen

import certifi

DEFAULT_RPC_URL = "https://ethereum-rpc.publicnode.com"
_ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")

# Read-only public JSON-RPC endpoints per supported EVM chain. All are https
# public nodes (no key, no signing). native_symbol is the chain's gas coin.
CHAIN_REGISTRY: dict[int, dict[str, str]] = {
    1: {"name": "ethereum", "rpc_url": "https://ethereum-rpc.publicnode.com", "native_symbol": "ETH"},
    8453: {"name": "base", "rpc_url": "https://base-rpc.publicnode.com", "native_symbol": "ETH"},
    42161: {"name": "arbitrum", "rpc_url": "https://arbitrum-one-rpc.publicnode.com", "native_symbol": "ETH"},
    10: {"name": "optimism", "rpc_url": "https://optimism-rpc.publicnode.com", "native_symbol": "ETH"},
    137: {"name": "polygon", "rpc_url": "https://polygon-bor-rpc.publicnode.com", "native_symbol": "POL"},
}

# Human-friendly aliases that resolve to a canonical chain_id.
_CHAIN_ALIASES: dict[str, int] = {
    "ethereum": 1, "eth": 1, "mainnet": 1, "eth-mainnet": 1, "1": 1,
    "base": 8453, "base-mainnet": 8453, "8453": 8453,
    "arbitrum": 42161, "arbitrum-one": 42161, "arb": 42161, "42161": 42161,
    "optimism": 10, "op": 10, "op-mainnet": 10, "10": 10,
    "polygon": 137, "matic": 137, "pol": 137, "137": 137,
}


def resolve_chain(chain: str | int) -> tuple[int, dict[str, str]]:
    """Resolve a chain name or id to (chain_id, registry spec). Fail-closed on
    anything not in the read-only registry so a typo never silently reads the
    wrong network."""
    if isinstance(chain, int):
        chain_id = chain
    else:
        key = str(chain or "").strip().lower().replace(" ", "-")
        if key not in _CHAIN_ALIASES:
            raise EvmRpcError(f"unsupported or unknown EVM chain: {chain!r}")
        chain_id = _CHAIN_ALIASES[key]
    spec = CHAIN_REGISTRY.get(chain_id)
    if spec is None:
        raise EvmRpcError(f"unsupported EVM chain_id: {chain_id}")
    return chain_id, spec
# keccak256("balanceOf(address)") first 4 bytes
_BALANCE_OF_SELECTOR = "0x70a08231"
# keccak256("allowance(address,address)") first 4 bytes
_ALLOWANCE_SELECTOR = "0xdd62ed3e"
# ERC-20 "unlimited" approval sentinel (max uint256)
UNLIMITED_ALLOWANCE = 2**256 - 1
_ALLOWED_RPC_METHODS = frozenset({"eth_chainId", "eth_blockNumber", "eth_getBalance", "eth_call"})


class EvmRpcError(ValueError):
    pass


def _tls_context() -> ssl.SSLContext:
    return ssl.create_default_context(cafile=certifi.where())


def validate_evm_address(address: str) -> str:
    value = str(address or "").strip()
    if not _ADDRESS_PATTERN.match(value):
        raise EvmRpcError("a public 0x EVM address is required")
    return value


class EvmRpcReadOnlyAdapter:
    provider = "evm_rpc_readonly"

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        timeout_seconds: int = 15,
        transport: Any | None = None,
        expected_chain_id: int | None = None,
        native_symbol: str | None = None,
    ):
        self.rpc_url = str(rpc_url or DEFAULT_RPC_URL).strip()
        if not self.rpc_url.startswith("https://"):
            raise EvmRpcError("rpc_url must be an https endpoint")
        self.timeout_seconds = timeout_seconds
        self.transport = transport or self._request
        self.expected_chain_id = expected_chain_id
        self.native_symbol = native_symbol or "ETH"

    @classmethod
    def for_chain(
        cls,
        chain: str | int,
        *,
        rpc_url: str | None = None,
        timeout_seconds: int = 15,
        transport: Any | None = None,
    ) -> "EvmRpcReadOnlyAdapter":
        """Build an adapter for a named/known chain, using its default public
        read-only node unless an explicit rpc_url override is supplied."""
        chain_id, spec = resolve_chain(chain)
        return cls(
            rpc_url=rpc_url or spec["rpc_url"],
            timeout_seconds=timeout_seconds,
            transport=transport,
            expected_chain_id=chain_id,
            native_symbol=spec["native_symbol"],
        )

    def chain_id(self) -> int:
        raw = self._call("eth_chainId", [])
        if not re.fullmatch(r'0x[0-9a-fA-F]{1,64}', raw):
            raise EvmRpcError('invalid RPC chain identity')
        return int(raw, 16)

    def verify_chain(self) -> int | None:
        """Fail-closed guard: confirm the node actually serves the chain we
        think it does. Prevents reading a Base wallet against a mainnet node
        (or vice versa). No-op when no chain is expected (e.g. a raw rpc_url
        override), so it costs an extra call only when there is something to
        enforce."""
        if self.expected_chain_id is None:
            return None
        actual = self.chain_id()
        if actual != self.expected_chain_id:
            raise EvmRpcError(
                f"rpc endpoint chain_id {actual} does not match expected {self.expected_chain_id}"
            )
        return actual

    def get_native_balance(self, address: str) -> float:
        """Native coin balance in whole units (ETH for mainnet)."""
        checked = validate_evm_address(address)
        raw = self._call("eth_getBalance", [checked, "latest"])
        return int(raw, 16) / 10**18

    def read_wallet_snapshot(self, address: str, contract_address: str | None = None) -> dict:
        """Pin public balance reads to an observed height, keeping exact units.

        This is an observation, not a finality or token-price assertion. Token
        decimals are read from the same contract and block; ticker names are
        deliberately not used to identify or value contracts.
        """
        holder = validate_evm_address(address)
        contract = validate_evm_address(contract_address) if contract_address else None
        if self.expected_chain_id is None:
            raise EvmRpcError('a verified expected chain is required for a snapshot')
        self.verify_chain()
        block = self._call("eth_blockNumber", [])

        def uint(raw):
            try:
                if not re.fullmatch(r'0x[0-9a-fA-F]{1,64}', raw):
                    raise ValueError()
                number = int(raw, 16)
                if number < 0 or number >= 2**256:
                    raise ValueError()
                return number
            except (ValueError, AttributeError) as exc:
                raise EvmRpcError('invalid unsigned RPC value') from exc

        height = uint(block)
        if height > 2**53 - 1:
            raise EvmRpcError('invalid block height')
        tag = hex(height)

        def units(raw, decimals):
            with localcontext() as ctx:
                ctx.prec = 100
                return format(Decimal(uint(raw)) / (Decimal(10) ** decimals), 'f')

        balances = [{'symbol': self.native_symbol, 'contract_address': None,
                     'decimals': 18, 'amount': units(self._call('eth_getBalance', [holder, tag]), 18)}]
        if contract:
            decimals = uint(self._call('eth_call', [{'to': contract, 'data': '0x313ce567'}, tag]))
            if decimals > 36:
                raise EvmRpcError('token decimals must be between 0 and 36')
            data = _BALANCE_OF_SELECTOR + holder[2:].lower().rjust(64, '0')
            raw = self._call('eth_call', [{'to': contract, 'data': data}, tag])
            balances.append({'symbol': 'ERC20', 'contract_address': contract.lower(),
                             'decimals': decimals, 'amount': units(raw, decimals)})
        return {'chain_id': str(self.expected_chain_id), 'block_number': height, 'balances': balances}

    def get_erc20_balance(self, token_address: str, holder_address: str, *, decimals: int = 18) -> float:
        token = validate_evm_address(token_address)
        holder = validate_evm_address(holder_address)
        data = _BALANCE_OF_SELECTOR + holder[2:].lower().rjust(64, "0")
        raw = self._call("eth_call", [{"to": token, "data": data}, "latest"])
        if raw in {"0x", ""}:
            raise EvmRpcError("token contract returned no balance data")
        if decimals < 0 or decimals > 36:
            raise EvmRpcError("token decimals must be between 0 and 36")
        return int(raw, 16) / 10**decimals

    def get_erc20_allowance(
        self,
        token_address: str,
        owner_address: str,
        spender_address: str,
        *,
        decimals: int = 18,
    ) -> tuple[float, bool]:
        """Returns (allowance in token units, is_unlimited). Read-only: this
        queries an existing approval; it can never create or change one."""
        token = validate_evm_address(token_address)
        owner = validate_evm_address(owner_address)
        spender = validate_evm_address(spender_address)
        data = _ALLOWANCE_SELECTOR + owner[2:].lower().rjust(64, "0") + spender[2:].lower().rjust(64, "0")
        raw = self._call("eth_call", [{"to": token, "data": data}, "latest"])
        if raw in {"0x", ""}:
            raise EvmRpcError("token contract returned no allowance data")
        if decimals < 0 or decimals > 36:
            raise EvmRpcError("token decimals must be between 0 and 36")
        raw_amount = int(raw, 16)
        # Treat anything within a factor of 2 of max uint256 as an unlimited approval.
        is_unlimited = raw_amount >= UNLIMITED_ALLOWANCE // 2
        return raw_amount / 10**decimals, is_unlimited

    def _call(self, method: str, params: list[Any]) -> str:
        if method not in _ALLOWED_RPC_METHODS:
            raise EvmRpcError(f"rpc method is outside the read-only allowlist: {method}")
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        response = self.transport(payload)
        if not isinstance(response, dict):
            raise EvmRpcError("rpc endpoint returned an invalid response")
        if response.get("error"):
            raise EvmRpcError(f"rpc error: {str(response['error'])[:200]}")
        result = response.get("result")
        if not isinstance(result, str):
            raise EvmRpcError("rpc response missing result")
        return result

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = Request(
            self.rpc_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Several public RPC providers reject requests without a UA.
                "User-Agent": "ai-trading-os/0.1 read-only",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds, context=_tls_context()) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise EvmRpcError(f"rpc request failed: {str(exc)[:200]}") from exc
