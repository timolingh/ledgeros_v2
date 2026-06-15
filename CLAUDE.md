## Project-Specific Guidelines: Accounting Core System

This system handles financial records. Treat accounting behavior as high-risk.

Before coding:
- State domain assumptions explicitly.
- Identify whether the change affects ledger entries, reports, balances, payments, invoices, reconciliations, taxes, 
owner statements, tenant ledgers, or audit trails.
- If accounting treatment is ambiguous, stop and ask.
- Before changing ledger behavior, read `docs/accounting-core-invariants.md` and keep code, tests, and docs aligned with it.

Simplicity:
- Prefer explicit domain functions over generalized abstractions.
- Do not create a generic accounting engine unless multiple concrete use cases already require it.
- Avoid speculative configurability.

Surgical changes:
- Every changed line must trace to the requested behavior.
- Do not refactor unrelated ledger, payment, or reporting code.
- Do not rename accounts, enums, or transaction types without migration and test coverage.

Goal-driven execution:
- For every accounting change, define success using examples:
  - expected journal entries
  - expected account balances
  - expected owner statement line items
  - expected tenant ledger entries
  - expected report totals
- Write or update tests before implementation when behavior changes.

## Epic Implementation Discipline

Before implementing or reviewing any epic, read and follow:

- `docs/accounting-core-invariants.md`
- `docs/epic-implementation-guardrails.md`
- `docs/reporting-invariants.md`

Every epic must include a requirement traceability matrix, explicit deferred/out-of-scope items, automated tests for implemented accounting invariants, and Docker-ready manual acceptance checks.

## Runtime Policy

Run the application and all validation from containers.

- Start the app with Docker Compose.
- Run tests and Django management checks inside the `web` service container.
- Do not assume host Python, host dependencies, or host test execution are available.
- If a command can be run in the container, use the container path first.

## Anti-Slop Engineering Principles

1. **Run the code, not just the generator.**  
   Generated code is not complete until the relevant runtime checks pass. For Django work, at minimum run `./scripts/check.sh` or its equivalent commands: `python manage.py check`, `python manage.py makemigrations --check --dry-run`, migrations, relevant management commands, and tests before claiming the task is done.

2. **Preserve domain invariants in executable tests.**  
   Any business rule described in the PRD or epic must have a corresponding test. For accounting, this includes balanced journal entries, closed-period posting rejection, draft exclusion from balances, reversal behavior, audit-log creation, and immutability of posted entries.

3. **Do not bypass the service layer for state-changing operations.**  
   Views, serializers, admin actions, management commands, and future integrations must call domain services for mutations. They must not directly change critical fields such as journal status, period status, posted timestamps, reversal links, or audit records.
   - Django admin, API, and management commands must share the same application write path for the same accounting behavior.
   - If a state-changing action exists in the API, the Django path must invoke the same service entrypoint rather than reimplementing the mutation or editing model fields directly.
   - Read-only convenience fields may differ by surface, but the underlying accounting transition must remain one service call.

4. **Avoid polished scaffolds that are not wired together.**  
   New files must be internally consistent across imports, model fields, admin config, serializers, migrations, URLs, tests, and commands. If a symbol is referenced, it must exist. If a field is renamed, every caller must be updated. No handoff should rely on the user discovering integration errors.

5. **Separate implemented scope from future scope.**  
   Follow the approved epic/PRD boundary. Do not implement later-epic features early just because they are easy to scaffold. If a future hook is needed, keep it minimal, documented, and covered by tests without pretending the later feature is complete.
