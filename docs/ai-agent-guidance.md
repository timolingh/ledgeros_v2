# AI Agent Guidance for LedgerOS

This document is mandatory guidance for AI agents changing LedgerOS. Follow it strictly.

## 1. Read first

Before coding, read:

```text
CLAUDE.md
docs/technical-spec.md
docs/accounting-core-invariants.md
docs/reporting-invariants.md
docs/epic-implementation-guardrails.md
docs/api-auth-idempotency.md
docs/api-client-config-schema.md
```

For UI/client work, also read:

```text
docs/user-manual.md
docs/feature-roadmap.md
```

## 2. Non-negotiable accounting rules

Do not violate these rules:

1. Draft journal entries do not affect balances.
2. Posted journal entries affect balances.
3. Posted accounting facts are not destructively edited.
4. Corrections happen through reversal, credit, refund, or explicit adjustment workflows.
5. Journal entries must balance debits and credits.
6. Closed and locked periods reject postings.
7. Operational AR/AP/banking records must reconcile to GL impact.
8. Reports must use posted accounting data and documented sign rules.
9. API write retries must not create duplicate postings.
10. Secrets must never be committed or logged.

## 3. Use the correct layer

Use this rule:

```text
models: data and constraints
services: state-changing workflows
selectors: read-side questions
api: thin transport layer
admin: transitional operator surface
tests: executable invariants
docs: source of truth for decisions and behavior
```

Do not put core accounting decisions in serializers, views, templates, or admin methods.

## 4. Required planning before code

Before changing code, produce a short plan with:

- target behavior,
- affected domain objects,
- service functions to add/change,
- API/admin changes,
- migrations needed,
- tests needed,
- docs to update,
- explicit deferred items.

If accounting behavior is ambiguous, stop and ask for clarification.

## 5. Model-change rules

When changing models:

- Add migrations intentionally.
- Preserve existing data unless a migration explicitly transforms it.
- Add database constraints for accounting uniqueness/integrity when appropriate.
- Avoid nullable fields unless there is a real transitional reason.
- Do not add generic JSON blobs for core accounting state unless clearly justified.
- Update admin, serializers, tests, and docs.

Run:

```bash
docker compose run --rm web python manage.py makemigrations --check --dry-run
```

If migrations are required, generate and inspect them.

## 6. Service-change rules

When changing services:

- Validate inputs before creating accounting records.
- Use transactions for multi-record accounting workflows.
- Create operational record and GL impact together when required.
- Audit successful material actions.
- Preserve idempotency for external API ingestion.
- Do not bypass period validation.
- Do not bypass account active/posting validation.

Every service change needs tests.

## 7. API-change rules

When changing APIs:

- Keep views thin.
- Keep serializers focused on input/output shape.
- Call services for accounting mutations.
- Disable generic destructive writes where unsafe.
- Use explicit actions for post, reverse, apply, match, complete, void, or similar workflows.
- Preserve HMAC authentication for external writes.
- Enforce scopes and allowed event types.
- Preserve idempotency response replay.
- Do not add bank-ingestion endpoints unless explicitly requested.

## 8. Reporting-change rules

When changing reporting:

- Read `docs/reporting-invariants.md` first.
- Define whether the report is as-of or period-based.
- Define accrual/cash basis semantics.
- Define sign rules.
- Define included statuses.
- Add drill-down or document why it is deferred.
- Test contra revenue and contra expense.
- Test prior-period exclusion for period reports.
- Test draft exclusion.

## 9. Bookkeeper UI rules

When building a bookkeeper UI:

- Treat Django Admin as transitional only.
- Build safe workflow screens, not raw database editors.
- Do not expose direct status editing.
- Do not allow posted record deletion.
- Use explicit service-backed actions.
- Show validation errors clearly.
- Show audit history.
- Keep accounting jargon minimal for non-technical users.

Required screens:

- Dashboard
- Customers
- Invoices
- Customer payments
- Vendors
- Bills
- Vendor payments
- Bank accounts
- Bank transactions
- Bank reconciliation
- Reports
- Audit/history

## 10. API client rules

When building an API client:

- Read API secrets from environment or a secrets manager.
- Never hard-code secrets.
- Sign write requests with HMAC.
- Use a unique nonce for every request.
- Use stable idempotency keys for each business operation.
- Retry network failures using the same idempotency key and a new nonce.
- Treat response replay as success.
- Do not log signatures or secrets.
- Log endpoint, client ID, external reference, idempotency key, and response code.

## 11. Required tests

For backend changes, add tests proving behavior.

Minimum expectations:

- Model constraints if schema changes.
- Service success and failure paths.
- GL/accounting impact for accounting workflows.
- API auth/permission behavior for API changes.
- Idempotency behavior for ingestion changes.
- Report totals and drill-downs for reporting changes.
- Regression tests for previously fixed bugs.

Do not claim completion without tests unless explicitly instructed to produce a design-only change.

## 12. Required Docker checks

Always run the application and test commands in containers.

Use the `web` service for Django runtime and checks:

```bash
docker compose up web
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest
```

Before handoff, run:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest
```

If dependencies or environment prevent running checks, say exactly what could not be run and why.

## 13. Documentation update rules

Update docs when behavior changes.

- User-facing operating behavior: update `docs/user-manual.md`.
- Architecture or decisions: update `docs/technical-spec.md`.
- Agent rules: update `docs/ai-agent-guidance.md`.
- Roadmap/deferred scope: update `docs/feature-roadmap.md`.
- Accounting invariants: update `docs/accounting-core-invariants.md` only when intentionally changing core rules.
- Reporting semantics: update `docs/reporting-invariants.md`.

Keep old epic READMEs as historical implementation notes. Do not delete them without explicit instruction.

## 14. Things agents must not do

Do not:

- Bypass services for state-changing accounting behavior.
- Mutate posted journal entries directly.
- Mark closed/locked periods as postable by accident.
- Add API-key-only accounting writes.
- Store HMAC secrets in YAML.
- Log secrets, signatures, or authorization headers.
- Invent accounting treatment silently.
- Add roadmap scope while pretending it is part of the current task.
- Add broad abstractions without a concrete current use case.
- Describe a partial feature as complete.
- Ignore failing tests.
- Remove old epic notes unless asked.

## 15. Handoff checklist

Every implementation handoff must include:

- Summary of changed behavior.
- Files changed.
- Migrations added, if any.
- Tests added/changed.
- Docker checks run.
- Deferred items.
- Known risks.
- Manual acceptance steps.
