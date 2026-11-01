# Fundraising Readiness Gap Analysis - 2026-06-19

This note evaluates the current product plan against a RMB 10M+ financing target. If the target is USD 10M+, the bar should be treated as a later seed or Series A standard: real production usage, stronger revenue/retention proof, and deeper compliance readiness would be required.

## Executive Assessment

The product is technically credible as a safe AI-native personal financial terminal demo. The strongest evidence is the differentiated wedge, the explicit safety boundary, the required thesis-to-review workflow, and the completed readiness/report packets across data, ledger, workflow, beta, stability, broker reconciliation, sidecar policy, and small pilot readiness.

The product is not yet financing-complete. The main gap is not another speculative trading feature. The main gap is proof that a narrow user segment will use and pay for the terminal with real read-only data, under a compliance-safe product boundary, in a production-grade environment.

Estimated readiness:

| Dimension | Current Readiness | Financing Interpretation |
| --- | ---: | --- |
| Engineering demo | 75-85% | Strong enough for a controlled founder-led demo. |
| Product narrative | 65-75% | Wedge is strong, but ICP and killer workflow need sharpening. |
| Safety architecture | 70-80% | Strong for pre-live stages; keep this as a fundraising advantage. |
| Real data/integration proof | 35-45% | Public/read-only and sample flows exist; authenticated accounts remain the key gap. |
| Production/security | 25-40% | Auth, roles, secrets, monitoring, backup, restore, and incident controls are not complete. |
| User/traction proof | 0-20% | No repo evidence of beta users, retention, revenue, LOIs, or paid pilots. |
| Compliance readiness | 25-40% | Strong internal safety principles, but no external legal/compliance memo or jurisdiction plan. |
| Fundraising materials | 10-25% | Product docs exist; investor deck, demo video, metrics dashboard, and data room still missing. |

Overall, the project is around 45-55% ready for a RMB 10M+ seed-style raise if the next milestone is a strong prototype plus committed pilots. It is around 20-30% ready for a USD 10M+ institutional round, because that would require stronger production usage, revenue, and compliance evidence.

## Current Strengths To Preserve

1. Differentiated wedge
   - The product is not "AI trading bot". It is a terminal that remembers investment logic, detects self-violation, and enforces a review loop.
   - This is materially better for investors than leading with autonomous trading.

2. Safety-first positioning
   - Defaults keep live trading disabled, automation at read-only level, Web3 read-only, no private keys, no withdrawal-enabled credentials, and no LLM direct execution.
   - This should remain a core fundraising point: the system is designed to avoid the most obvious regulatory and trust traps.

3. Workflow depth
   - The required trade flow covers constitution, playbook, thesis, gates, risk, behavior, approval, paper execution, journal, post-trade review, and monthly review.
   - The product is already closer to an operating system than a simple chatbot.

4. Readiness/reporting discipline
   - The 1-10 completion pass added certified sync plan, contract enforcement, reconciliation workbench, workflow packets, backtest research packet, beta invitation packet, stability packet, broker reconciliation plan, and small pilot go/no-go.
   - This creates strong demo material for "how the system says no" and "how it explains what is missing".

## Unfinished Work Blocking Strong Financing

### 1. ICP and Killer Workflow

Current product definition says "multi-asset investors", covering stocks, ETFs, crypto, CEX, stablecoins, and public wallets. That is directionally strong but too broad for a financing story.

Missing:

- Choose one beachhead ICP for the first raise.
- Define the one workflow the user opens the product for every day.
- Decide whether the buyer is a self-directed investor, active crypto/equity operator, family-office analyst, investment community operator, or advisor-like professional.
- Produce a sharp before/after demo script.

Financing target:

- One sentence: "For X user, this replaces Y workflow, because Z pain happens every week."
- One primary activation metric.
- One retention metric.

### 2. Real Read-Only Account Data

The current adapters are deliberately safe. That is good, but the financing demo needs at least one authenticated read-only integration path.

Missing:

- Real authenticated read-only broker adapter.
- Real authenticated read-only CEX adapter.
- Public wallet portfolio sync beyond metadata/sample flows.
- Statement download/import automation.
- Corporate actions, dividends, fees, tax-lot, cash movement normalization.
- Reconciliation-based data promotion rules.

Financing target:

- One complete read-only account connection with real positions, balances, transactions, freshness, and reconciliation status.
- No trading keys, no withdrawal keys, no signing.

### 3. Production Auth, Security, And Operations

The project has local health checks and stability packets, but production readiness is still mostly metadata/planning.

Missing:

- Authentication and session management.
- Role-based access control.
- Secret manager integration.
- Environment separation: local, staging, production.
- Deployment automation.
- Monitoring provider wiring.
- Error tracking and alerting.
- Backup automation.
- Restore drill executed in isolated infrastructure.
- Audit retention policy.
- Incident response runbook.

Financing target:

- A private beta deployment that can safely host external users and real read-only account data.
- A lightweight SOC2-style control map, even if not certified.

### 4. Compliance Boundary And Legal Memo

The product already says it should not become an investment advisor, profit-promise product, or black-box trading bot. That needs to become an externally reviewable compliance boundary.

Missing:

- Jurisdiction and market entry plan.
- Legal memo on investment advice boundary.
- Product language policy: education, workflow automation, and self-discipline versus personalized securities advice.
- Disclaimers and user acknowledgements.
- AI output review policy.
- Conflict-of-interest policy.
- Marketing claims policy.
- Data privacy and retention policy.
- Crypto/CEX/wallet custody and non-custody boundary.

Financing target:

- An investor can see that the company understands where the regulatory cliffs are and has designed around them.

### 5. AI Quality, Evals, And Explainability

The repo includes mock AI and validated reports, but financing-grade AI needs measured quality and trust controls.

Missing:

- Real LLM provider integration behind a safe adapter.
- Eval suite for hallucination, unsupported claims, stale data usage, and order-leakage attempts.
- Prompt/version registry.
- Source citation and evidence packet for every research conclusion.
- Model fallback and disable policy.
- Red-team scenarios for financial advice leakage.

Financing target:

- Show that AI does not just sound plausible; it obeys data contracts, cites sources, and fails closed.

### 6. Beta User And Traction System

No repository evidence yet shows real users, waitlist conversion, retention, revenue, or LOIs.

Missing:

- Landing/waitlist funnel.
- Private beta invite workflow that actually sends and tracks invites.
- Analytics events across activation, daily use, thesis creation, gate checks, review completion, and data sync.
- User interview repository.
- Pricing tests.
- LOI or paid pilot templates.
- Founder-led onboarding script.

Financing target:

- 10-30 high-quality beta users or 3-5 serious pilot conversations.
- At least one durable usage loop: weekly active use, repeated thesis review, or repeated account reconciliation.

### 7. Product UX Completion

The frontend has major workspaces, but the investor/user experience still needs to feel like a coherent terminal, not only a surface over many endpoints.

Missing:

- First-run onboarding.
- Guided demo workspace.
- Real connection setup flows.
- Clear empty states.
- Action queue that moves the user through a daily workflow.
- Drilldowns for order closure, review quality, data trust, and reconciliation.
- Mobile polish for review/check workflows.
- A polished demo script and demo seed matching the financing narrative.

Financing target:

- A 7-minute demo where a non-builder understands the product without reading docs.

### 8. Business Model And Go-To-Market

The engineering plan is much clearer than the commercial plan.

Missing:

- Pricing model: subscription, pro terminal, community/creator edition, advisor/team tier, or self-hosted license.
- ICP-specific willingness-to-pay evidence.
- Distribution channel: investor community, content, broker partnerships, crypto communities, family offices, advisors, or B2B SaaS.
- CAC hypothesis and conversion funnel.
- Gross margin and infra cost model.
- Expansion path from individual terminal to team/compliance terminal.

Financing target:

- One believable wedge channel and one pricing page.
- Early conversion evidence, even if small.

### 9. Fundraising Data Room

The repo has product documents, but not an investor-ready package.

Missing:

- Pitch deck.
- Product demo video.
- One-page memo.
- Market map.
- Competitive comparison.
- Technical architecture summary.
- Compliance boundary memo.
- Security/ops summary.
- Product metrics dashboard.
- Financial model and use-of-funds plan.
- 12-month hiring and milestone plan.

Financing target:

- A complete investor packet that lets a warm intro become a serious first meeting.

### 10. Live Execution Strategy

The current decision to keep real live trading disabled is correct. The missing work is not to rush live execution, but to prove a responsible path toward it.

Missing:

- Broker sandbox adapter.
- Explicit account allowlist.
- Sandbox order-state reconciliation.
- Idempotency keys and cancel/replace path.
- Signed approval packet.
- Small-notional pilot policy.
- Kill switch exercise.
- Rollback drill.

Financing target:

- Investors should see live execution as a later controlled option, not the current dependency for value.

## Ten-Step Development Plan Toward Financing Readiness

### Plan 1 - Narrow The Fundraising Wedge

Deliverables:

- ICP decision memo.
- Daily killer workflow definition.
- Before/after demo script.
- Success metrics: activation, weekly retention, paid intent.

Exit criteria:

- A 60-second pitch is understandable without product docs.

### Plan 2 - Build Investor Demo Path

Deliverables:

- Seeded demo workspace aligned to the pitch.
- One-click demo reset.
- Guided terminal path: sync data, inspect thesis, gate order, paper fill, review.
- Demo video outline.

Exit criteria:

- 7-minute demo runs without developer narration.

### Plan 3 - Ship First Real Read-Only Integration

Deliverables:

- One broker or CEX read-only adapter.
- Secret-reference-only auth.
- Positions, balances, transactions, freshness, and account snapshot.
- Audit log and fail-closed sync.

Exit criteria:

- A real account can sync without trading authority.

### Plan 4 - Complete Ledger And Reconciliation MVP

Deliverables:

- Normalize fills, fees, cash, dividends, transfers, and basic corporate actions.
- Statement reconciliation UI.
- Dataset promotion rules after reconciliation.
- Reconciliation exception workflow.

Exit criteria:

- The product can explain why portfolio records are trusted or blocked.

### Plan 5 - Production Security Foundation

Deliverables:

- Auth.
- RBAC.
- Secret manager.
- Staging/prod config.
- Audit retention.
- Security checklist.

Exit criteria:

- External beta can use real read-only data without local-only assumptions.

### Plan 6 - AI Trust And Evaluation Layer

Deliverables:

- Real LLM adapter behind safe policy.
- Eval suite for hallucination, stale data, unsupported claims, advice leakage, and executable order leakage.
- Citation/evidence packets.
- Prompt/version registry.

Exit criteria:

- AI outputs can be reviewed, reproduced, and blocked.

### Plan 7 - Private Beta And Metrics

Deliverables:

- Invite workflow.
- Waitlist/landing page.
- Analytics events.
- User interview template.
- Feedback tagging.
- Activation and retention dashboard.

Exit criteria:

- 10-30 beta users or 3-5 qualified pilot prospects produce measurable behavior.

### Plan 8 - Product UX Polish

Deliverables:

- First-run onboarding.
- Empty states.
- Daily action queue polish.
- Reconciliation and review drilldowns.
- Mobile review flow.
- Investor-facing demo mode.

Exit criteria:

- Product feels like one terminal, not a collection of panels.

### Plan 9 - Fundraising Data Room

Deliverables:

- Deck.
- One-pager.
- Demo video.
- Technical architecture summary.
- Compliance memo.
- Security/ops summary.
- Financial model.
- Use-of-funds and hiring plan.

Exit criteria:

- Materials are ready for warm intros.

### Plan 10 - Controlled Live Sandbox Proof

Deliverables:

- Broker sandbox adapter.
- Allowlist.
- Signed approval packet.
- Order-state reconciliation.
- Kill switch and rollback drill.
- Small pilot policy.

Exit criteria:

- Live execution remains gated, but the path is credible and auditable.

## Recommended Financing Milestones

Before opening a RMB 10M+ seed-style raise:

1. One narrow ICP and a crisp wedge.
2. One polished 7-minute demo.
3. One real read-only account integration.
4. A private beta deployment with auth, RBAC, secrets, monitoring, and backups.
5. At least 10-30 beta users, 3-5 qualified pilot prospects, or signed LOIs.
6. Usage metrics showing repeated behavior.
7. Compliance boundary memo.
8. Investor deck, one-pager, demo video, and data room.

Before opening a USD 10M+ raise:

1. Real production usage.
2. Strong retention or revenue.
3. Multiple real read-only integrations.
4. Mature AI eval and governance layer.
5. Clear regulatory and jurisdiction strategy.
6. Repeatable GTM channel.
7. Evidence that the product can become either a personal terminal network or an institutional workflow platform.

## External Calibration

- Investor.gov defines an investment adviser as a firm or person that, for compensation, provides investment advice about securities or issues regular reports/analyses regarding securities. This makes the product boundary around education, workflow automation, and self-discipline important.
- FINRA Regulatory Notice 24-09 says existing securities rules continue to apply when member firms use generative AI or similar tools. Even if the first market is not a regulated member firm product, this is the right governance bar for investor diligence.
- The SEC's 2023 predictive data analytics proposal highlights regulatory concern when technologies interact with investors and create conflicts of interest. The product should keep conflict, recommendation, and personalization controls explicit.
- NIST AI RMF frames trustworthy AI as something managed through design, development, use, and evaluation. The project's eval/audit/data-contract work should be shaped into an investor-readable AI risk management story.

## Bottom Line

The next financing-relevant stage should not be "build live trading". It should be:

1. prove one user segment,
2. connect one real read-only account source,
3. make the terminal production-safe for beta users,
4. show repeated usage or paid intent,
5. package the safety-first architecture into a credible investor story.

That path fits the current product DNA and avoids weakening the strongest thing the project already has: a serious, auditable system that helps investors keep discipline instead of chasing an unsafe black-box trading promise.
