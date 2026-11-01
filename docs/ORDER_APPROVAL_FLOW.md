# Order Approval Flow (Draft)

## Stages

1. Intent created (strategy/signal engine)
2. Risk pre-checks (hard constraints)
3. Approval request (human UI)
4. Human decision: approve / modify / reject
5. Execution (paper/live adapter)
6. Post-trade reconciliation + portfolio update

## Required metadata

- intent id
- rationale
- max slippage / limit price policy
- stop / take-profit policy (if any)
- risk budget used
