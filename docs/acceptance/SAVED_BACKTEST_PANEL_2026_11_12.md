# Saved backtests in the existing indicator page

The original indicator strategy backtest page now includes an explicit read action for saved backend backtests. It retains script editing and the marked fixed UI examples. It does not run the current script or promote a result into a strategy or order. Records show their own date range, original parameters, data contract, status, results and blockers; local candles are not labelled verified exchange data. The list belongs to the authenticated user, may include other instruments, and has no trading-account binding.

The list endpoint requires read permission, explicitly filters the actor user in addition to tenant enforcement, constrains limit to 1..100 and returns no-store. The panel verifies row ownership, explicit execution_available=false and unique IDs, aborting/hiding results when session or terminal context changes. There is no sample fallback on API failure. It displays the 100-row truncation possibility.

Validation: backtest API/service suite 15 passed including foreign-user empty list, bounded limit and no-store. External terminal suite134 passed, repository mirror138 passed; terminal build passed with existing chunk-size warning. Local backend restarted with existing scheduler/live-disabled launcher; health200. No paid provider, actual broker trade or real account backtest was performed. Browser acceptance and arbitrary editor-script engine integration remain incomplete. This panel reads existing backend runs; it does not implement arbitrary-script backtesting or all strategy AI actions.

## Explicit research preparation

Each owned saved record can request the existing backend research packet. That endpoint now requires readiness:write, checks actor ownership, and returns no-store. The panel checks run/playbook linkage and explicit no-execution/no-order flags before preview. A separate user action prepares the entire packet as a bounded untrusted historical-text question in the existing AI dock, with market attachment disabled and manual send still required. The question explicitly disclaims current-script execution, current-account performance, independently verified history and formal evidence-snapshot citations. Over 4000 characters is rejected rather than silently truncated by the dock. No provider was called. This text handoff is not the missing dedicated immutable backtest evidence adapter.

Validation: backend backtest suite16 passed (foreign packet404, no-store, no drafts), external terminal135 passed, mirror139 passed; build passed. Backend restarted with the same disabled scheduler/live defaults. Browser/model delivery and actual arbitrary script execution remain unverified/unimplemented.

## Frozen source artifact

The panel now requests POST /backtest-runs/{run}/research-material. This creates a private DataSnapshot containing detached original run parameters/results, research packet, run dates/status and capture time, with canonical SHA-256 and a separate owner-scoped audit hash. GET on the run/material pair validates ownership, schema, flags, hash and audit linkage. It does not rewrite the source run or grant trading permission. Generic data-source snapshot lists exclude the private material type. An existing run changing later leaves its saved artifact unchanged. Text handoff includes artifact ID/hash/time, but the AI request still does not dereference and validate this as a dedicated evidence attachment; no formal AI citation claim is made.

Controlled tests: original parameters changed after capture leave artifact unchanged; foreign reads/preparation and wrong-run paths reject; modified content even with recomputed hash rejects against audit; no order drafts. Backend17 passed, external terminal136 and mirror140 passed; build passed. Backend restarted, no model calls or real trades. Browser acceptance and dedicated AI reference/citation binding remain outstanding.

## Full material export

The frozen material preview includes a JSON download of the entire validated artifact, including original parameters/results, source packet, capture time, snapshot ID and hash. Export rechecks the current session/context and does not truncate to the AI question limit. It uses the already loaded artifact, makes no additional backend/model request, and grants no trading authority. Terminal production build passed. Actual browser download acceptance remains outstanding.

## AI reference freshness boundary

The dedicated reference resolver accepts only snapshot ID, run ID and hash, revalidates owner/audit/hash and permits a 600-second age with at most30 seconds future clock skew. Controlled boundary tests accept600/-30 and reject601/-31 with ai_backtest_stale. Expired material remains readable as historical evidence. Nine material/reference tests pass. This resolver is not yet called by research chat, and does not complete citation binding.

## Dedicated chat integration supersedes the earlier text-only state

The saved-record action now prepares a dedicated backtest attachment for the original AI dock. The user explicitly selects it and sends manually. Only the reference is sent; owner/workspace/freshness are checked locally, and the server re-resolves hash/audit/ownership and timing. Mixed specialized attachments are blocked. The shared chat status/configuration/preflight constructs the configured provider, then the internal orchestrator freezes a private request artifact, builds bounded BT1 evidence, validates report schema/type/agent/snapshot identity and citations before/after output limits, and stores validated success or failure. No actual paid model was called during acceptance.

Controlled HTTP tests demonstrate a valid referenced response and rejected uncited response; wrong reference, foreign ownership and mixed strategy attachments reject before provider construction. The original AI reply displays BT1 provenance, and Markdown export retains strategy/backtest IDs plus backtest hash/time/date range. The attachment can be removed without switching workspaces. Raw saved-material JSON export remains available.

Most recent external terminal tests139 and mirror143 pass. Latest terminal production build passes and served feature entry returns200. Earlier related backend64-test regression passed before the latest front-only display/export changes. Browser send/download/refresh, actual provider acceptance and all-page adapter coverage remain unverified. The arbitrary editor script runner is still absent; no saved-result or chat work substitutes for that requirement.
