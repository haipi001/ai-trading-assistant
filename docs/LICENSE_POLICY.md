# License Policy

This repository is a self-developed control system with strict rules for open-source reuse.

This policy reflects upstream license checks performed on 2026-06-04. Re-verify before any future code reuse.

## Core Rule

Do not copy large blocks of code from external repositories into the main codebase.

The following modules must remain self-developed:

- InvestmentConstitution
- StrategyPlaybook
- InvestmentThesis
- DecisionGates
- RiskEngine
- BehaviorEngine
- AutomationPolicy
- OrderWorkflow
- ApprovalWorkflow
- AuditLog
- MonthlyDecisionReview

## License Matrix

| License | Main-Codebase Copying | Default Decision |
| --- | --- | --- |
| MIT | Small isolated reuse may be allowed with attribution | Allowed only after audit |
| Apache-2.0 | Small isolated reuse may be allowed with attribution and notice preservation | Allowed only after audit |
| BSD | Small isolated reuse may be allowed with attribution | Allowed only after audit |
| LGPL | Treat as high-friction for copied core code | Prefer dependency or sidecar |
| GPL | Copied code is not allowed in the main codebase by default | Use sidecar or reference only |
| AGPL | Copied code is not allowed in the main codebase by default | Use sidecar or reference only |
| Unknown / missing | No copying allowed | Reference only until clarified |

## Categories That Must Not Be Copied

- broker credential handling
- exchange order-routing code
- wallet signing logic
- seed phrase or private-key handling
- external risk engines as the project safety core
- wholesale UI cloning
- logos, names, and brand assets

## Required Review Before Reuse

Before reusing any external code:

1. Verify the current upstream license from the official repository.
2. Decide whether the project is a `reference`, `dependency`, `sidecar`, or `small isolated reuse`.
3. Record the decision in `docs/OPEN_SOURCE_MAP.md`.
4. If any source code is copied or adapted, add an entry to `THIRD_PARTY_NOTICES.md`.
5. Preserve all required copyright, notice, and license text.
6. Keep the reused module outside the main control path unless the architecture explicitly permits it.

## Default Integration Preference

Use these options in order of preference:

1. reference
2. dependency
3. sidecar
4. small isolated reuse

Copying code is the last resort, not the default.

## Enforcement

If the license, attribution duty, or integration boundary is unclear:

- do not copy the code
- treat the project as reference only
- fail closed until the audit is complete
