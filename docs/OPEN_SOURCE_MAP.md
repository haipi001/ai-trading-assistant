# Open Source Map

This file tracks audited external projects that influence this repository.

License and usage decisions in this file were verified against the official upstream repositories on 2026-06-04.

## Usage Modes

- `reference`: study the architecture, workflow, data model, or UX only; no source-code copying
- `dependency`: install as a package and wrap behind local adapters
- `sidecar`: run as a separate service or tool with strict interfaces
- `small isolated reuse`: copy a narrow module only when the upstream license permits it and attribution is preserved

## Default Rules

- `MIT`, `Apache-2.0`, and `BSD` projects may allow small isolated reuse with attribution.
- `AGPL`, `GPL`, `LGPL`, or unknown-license projects must not be copied into the main codebase by default.
- Trading execution paths, wallet signing, credential handling, and full product UI must remain self-developed even when the upstream license is permissive.
- Every copied or adapted file must be recorded in `THIRD_PARTY_NOTICES.md`.

## Audited References

| Project | Repository | Verified License | Intended Usage | Code Copy Policy | Boundary Notes |
| --- | --- | --- | --- | --- | --- |
| Vibe-Trading | <https://github.com/HKUDS/Vibe-Trading> | MIT | `reference`, possible `small isolated reuse` | Allowed only for small isolated modules with attribution | Good fit for research workspace, skill registry, and MCP/tool-routing ideas. Do not turn it into the main control system. |
| FinceptTerminal | <https://github.com/Fincept-Corporation/FinceptTerminal> | AGPL-3.0 plus commercial licensing terms | `reference` only | No copying into the main codebase | Use for terminal information architecture only. Treat branding and UI as protected. Do not rely on older notes that describe it as permissive. |
| Ghostfolio | <https://github.com/ghostfolio/ghostfolio> | AGPL-3.0 | `reference` only | No copying into the main codebase | Useful for portfolio dashboard and allocation ideas only. |
| rotki | <https://github.com/rotki/rotki> | AGPL-3.0 | `reference`, possible `sidecar` | No copying into the main codebase | Useful for crypto accounting and privacy-first data modeling. If needed, integrate through exports or APIs. |
| OpenBB | <https://github.com/OpenBB-finance/OpenBB> | AGPL-3.0-only | `reference`, possible `sidecar` | No copying into the main codebase | Useful for data catalog, connector patterns, and research workflows. Prefer API or SDK integration boundaries. |
| LEAN | <https://github.com/QuantConnect/Lean> | Apache-2.0 | `reference`, possible future `sidecar` | Do not copy core engine paths into the main codebase | Useful for event-driven engine design and interface patterns. Execution authority must remain downstream of local gates and approvals. |
| NautilusTrader | <https://github.com/nautechsystems/nautilus_trader> | LGPL-3.0 | `reference`, possible future `sidecar` | No main-codebase copying by default | Useful for event-driven architecture ideas. Treat the engine as separable infrastructure, not as the control-plane core. |
| Freqtrade | <https://github.com/freqtrade/freqtrade> | GPL-3.0 | `sidecar` only | No copying into the main codebase | If ever used, it must receive only already-approved strategy or order instructions and return results through audited adapters. |
| Hummingbot | <https://github.com/hummingbot/hummingbot> | Apache-2.0 | `sidecar` only | No copying of execution paths into the main codebase | Even with a permissive license, keep market-making, arbitrage, signing, and connector execution isolated behind sidecar boundaries. |

## Approved Dependency Pattern

Prefer package dependencies over source-code copying for reusable libraries such as:

- `yfinance`
- `ccxt`
- `web3.py`
- `backtesting.py`
- `vectorbt`
- `PyPortfolioOpt`
- `Riskfolio-Lib`

Wrap each dependency behind a local adapter or service boundary so it can be replaced without changing core workflow logic.
