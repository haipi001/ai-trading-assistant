# Terminal drawers and interface follow-up — 2026-11-11

Local implementation slice; not production or live-trading acceptance.

## Behavior

- File entry displays an actionable HTTP link preserving the query and function hash. Start the loopback service with `terminal-ui/start.command`; canonical entry is http://127.0.0.1:8850/index.html?lay=1#DES/AAPL. File URLs cannot load the complete module workspace reliably.
- Native terminal pages can open a separate right drawer using the existing business components, without replacing the main page. Tool context is explicitly the market/account/instrument selected in the top integration toolbar; simulated terminal quotes are not AI evidence.
- The tool frame reuses the existing permission/context host. Same-origin and exact source-window checks gate its messages. A tool-activation handshake prevents the initial empty React state from closing the new drawer. Internal close and Esc remove the auxiliary frame and return focus to the opener.
- Auxiliary frames do not acquire panel-lock controls or collide with the main panel lock key. Embedded pages initialize from their supplied target and do not overwrite the standalone legacy navigation preference.
- Theme changes propagate to embedded tools. Locale switching covers coded navigation items, common business controls, tooltips and selected AI/settings labels. Research materials and user input remain verbatim. Full English coverage remains incomplete.

## Changed source

- `terminal-ui/index.html`: file-entry guidance and retry.
- `terminal-ui/integration/shell.js`, `shell.css`: global tools, drawer lifecycle, labels, focus and responsive styles.
- `terminal-ui/integration/panel-host.mjs`, `desk.mjs`: auxiliary context delivery and lock isolation.
- `src/main.jsx`, `src/terminal-feature.jsx`, `src/terminal-feature.css`: real component bridge, tool presentation, legacy navigation preservation.
- `src/terminal-language.js`: interface label and accessible attribute translation.
- `terminal-ui/tests/tool-drawer.test.mjs`: actual handler origin/source rejection, initial readiness and activation/close race regression.

Runtime sources and tests are synchronized between the external local terminal folder and repository mirror. Generated feature bundles remain build outputs.

## Verification

- `node --test terminal-ui/tests/*.test.mjs`: 52 passed, 0 failed (49 existing and 3 new drawer message tests).
- `npm run build:terminal`: passed.
- `npm run build:public`: passed; legacy export retained. Vite still reports the existing large-chunk warning.
- HTTP: 13 integration modules returned 200 with JavaScript MIME; compiled tool entry and referenced local assets returned 200.
- `git diff --check`: passed after generated CSS whitespace normalization.

Browser automation connection timed out. No actual click, screenshot, narrow-screen visual, real-provider AI, private-account, or production acceptance is claimed. Opening the HTTP URL was queued in Codex; queueing is not visual verification. Live execution stays disabled and Web3 remains read-only. No deployment performed.

Next: browser verification of native/business-page drawers across layouts, themes and locales, then remaining interface translations.

## Sidebar naming and drawer discoverability follow-up

Replaced generated `业务 · <page>` headings in `terminal-ui/app.js` with descriptive groups: 研究首页, 专业图表, 实时快讯, 新闻与研报, 策略, 链上研究, 资产管理, 账户与授权, 数据中心, 工具与帮助. Group labels participate in the existing language switch and all function codes remain intact.

`integration/shell.js` and `shell.css` now place a labelled collapse button in the sidebar header and retain a visible reopen button after collapse. The toolbar menu button also has visible text. Keyboard focus moves to the usable control after either operation, and the collapsed navigation row reserves room for its reopen button. External runtime and repository mirror synchronized.

Validation: `node --check` on app/shell scripts passed; all 52 existing tests passed; local shell resource HTTP 200. Browser connection timed out again, so visual positioning/click acceptance is pending. This follow-up changes static runtime files and did not deploy a public release.
