# LedgerOS Epic 5 API Ingestion and Config-Managed Integration Implementation

This document describes the Epic 5 implementation for LedgerOS, building on the foundational accounting core from Epic 1, the AR/AP workflows from Epic 2, the banking flows from Epic 3, and the reporting/tax work from Epic 4.

## Scope Implemented

- Accounting event ingestion API for invoices, bills, payments, credits, and refunds
- Hybrid API surface with resource-shaped endpoints and event-shaped payload semantics
- HMAC write authentication for API submissions
- Limited API-key support for explicitly configured low-risk client use cases
- YAML-managed API client configuration loading and validation
- Idempotency key handling with replay of the original success payload
- API request persistence for idempotency, nonce tracking, and replay-safe response storage
- External invoice/bill number preservation with uniqueness scoped per client plus entity
- Internal API-generated numbering for API-created invoices and bills
- Invoice, bill, payment, and credit event validation before posting
- Service-layer routing for all accounting mutations
- Audit logs for API submissions and authentication failures
- Docker-ready validation commands and manual API acceptance checks

## Structure

```text
apps/accounting/
  models/
    integration.py                # ApiRequestRecord idempotency/replay model
    ar_ap.py                      # External source client fields and uniqueness rules
  services/
    api_ingestion.py              # API client config loading, payload handling, request replay
    ar_ap.py                      # Existing AR/AP posting and credit services reused by API
    audit.py                      # Audit log creation helper
    writes.py                     # Undeposited Funds helper used by payment ingestion
  api/
    authentication.py             # HMAC/API-key authentication for API write requests
    ingestion_serializers.py      # API payload validation serializers
    views.py                      # API ingestion endpoints
    urls.py                       # API route registration
  migrations/
    0008_api_request_record_...   # API request record + external source client schema
  tests/
    test_api_ingestion.py         # Epic 5 API ingestion and replay tests
```

## Explicit Domain Assumptions

- MVP uses the hidden default entity for API submissions, so external clients do not provide `entity_id`.
- API write requests are authenticated before validation and posting.
- HMAC is the primary authentication path for write operations.
- Limited API-key support exists only for explicitly configured low-risk cases.
- API client configuration is YAML-managed, with secrets referenced through environment variables.
- Requests must include an idempotency key, either in the `Idempotency-Key` header or in the payload.
- Duplicate requests return the original success payload.
- Duplicate requests must not create duplicate ledger postings, duplicate journal entries, or duplicate auditable side effects.
- External invoice and bill numbers are preserved for API-submitted records and are unique per client plus entity.
- API-created invoices and bills can still receive internal numbering using API-specific prefixes.
- Refunds are implemented as a specialized credit-event path that reuses the existing credit-memo accounting services.
- Bank events are intentionally deferred from Epic 5 MVP.
- All state-changing accounting work still flows through the existing service layer.

## Requirement Traceability Matrix

| Requirement | Source | Status | Code location | Test / manual check |
|---|---|---|---|---|
| Submit accounting events via API | Epic 5 / PRD API-001 | Implemented | `apps/accounting/api/views.py`, `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Require idempotency key | Epic 5 / PRD API-002 | Implemented | `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Handle duplicate idempotency key | Epic 5 / PRD API-003 | Implemented | `apps/accounting/models/integration.py`, `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Validate event schema | Epic 5 / PRD API-004 | Implemented | `apps/accounting/api/ingestion_serializers.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Validate accounting mappings | Epic 5 / PRD API-005 | Implemented | `apps/accounting/api/ingestion_serializers.py`, `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Validate permissions and scopes | Epic 5 / PRD API-006, APIAUTH-003, APIAUTH-007 | Implemented | `apps/accounting/api/authentication.py`, `apps/accounting/api/views.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Return posting result | Epic 5 / PRD API-007 | Implemented | `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Store external reference | Epic 5 / PRD API-008, AR-011, AR-012 | Implemented | `apps/accounting/models/ar_ap.py`, `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Expose event status through replayable API record | Epic 5 / PRD API-009 | Implemented | `apps/accounting/models/integration.py`, `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| YAML API client configuration | Epic 5 / PRD APIAUTH-001, APIAUTH-013, CONFIG-020 | Implemented | `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| HMAC write authentication | Epic 5 / PRD APIAUTH-005 | Implemented | `apps/accounting/api/authentication.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Validate timestamp and nonce | Epic 5 / PRD APIAUTH-006, NFR-SEC-008 | Implemented | `apps/accounting/api/authentication.py`, `apps/accounting/models/integration.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Preserve external invoice numbers | Epic 5 / PRD AR-011, AR-012 | Implemented | `apps/accounting/models/ar_ap.py`, `apps/accounting/services/api_ingestion.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Support invoice, bill, payment, credit, and refund API families | Epic 5 / PRD API contract | Implemented | `apps/accounting/api/views.py`, `apps/accounting/api/ingestion_serializers.py` | `apps/accounting/tests/test_api_ingestion.py` |
| Docker validation path | Epic 5 / Epic guardrails | Implemented | `docker-compose.yml`, project Docker config | Manual commands below |
| Bank events | Epic 5 / Epic decision | Deferred | N/A | Deferred to a later epic or API expansion |

## Local Run

Starting from a running Docker environment:

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest apps/accounting/tests/test_api_ingestion.py -v
```

## API Client Configuration

Epic 5 loads API clients from YAML via `LEDGEROS_API_CLIENTS_CONFIG`.

Example:

```yaml
api_clients:
  - client_id: api_full
    enabled: true
    secret_env: LEDGEROS_API_CLIENT_FULL_SECRET
    scopes:
      - invoices
      - bills
      - payments
      - credits
    allowed_event_types:
      - invoice.post_requested
      - bill.post_requested
      - payment.post_requested
      - credit.post_requested
      - refund.post_requested
```

Secrets are supplied by environment variables, not plaintext YAML.

## Manual Acceptance Checks

Set up two environment secrets and the client config path, then use Docker to exercise the API:

```bash
export LEDGEROS_API_CLIENT_FULL_SECRET=full-secret
export LEDGEROS_API_CLIENT_INVOICE_ONLY_SECRET=invoice-secret
export LEDGEROS_API_CLIENTS_CONFIG=/path/to/api_clients.yml
```

If you're starting from a fresh database, load the chart of accounts and create an open period first:

```bash
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import create_accounting_period

create_accounting_period(
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    name="FY2026",
)
PY
```

Submit an invoice:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal

from apps.accounting.models import Account, Customer, Entity, Invoice, InvoiceLine
from apps.accounting.services import post_invoice

entity = Entity.get_default()
ar_account = Account.objects.get(entity=entity, account_code="1100")
customer, _ = Customer.objects.update_or_create(
    entity=entity,
    customer_code="API-CUST-001",
    defaults={"name": "API Ingestion Customer", "default_ar_account": ar_account},
)
revenue = Account.objects.get(entity=entity, account_code="4000")

invoice = Invoice.objects.create(
    entity=entity,
    customer=customer,
    invoice_number="API-INV-0001",
    external_invoice_number="EXT-INV-001",
    external_source_client_id="api_full",
    date=date(2026, 5, 1),
    due_date=date(2026, 6, 1),
    total_amount=Decimal("100.00"),
)

InvoiceLine.objects.create(invoice=invoice, account=revenue, line_description="Revenue", amount=Decimal("100.00"))
post_invoice(invoice=invoice, source="api")
print(invoice.status)
PY
```

Submit an API payment against an existing external invoice reference:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal

from apps.accounting.models import Entity, Invoice
from apps.accounting.services.api_ingestion import submit_payment_event

entity = Entity.get_default()
invoice = Invoice.objects.get(entity=entity, external_invoice_number="EXT-INV-001", external_source_client_id="api_full")

status_code, payload = submit_payment_event(
    client_id="api_full",
    idempotency_key="payment-demo-001",
    nonce="demo-nonce-001",
    payload={
        "source_type": "invoice",
        "source_reference": "EXT-INV-001",
        "payment_date": date(2026, 5, 10),
        "amount": Decimal("100.00"),
    },
)

print(status_code)
print(payload["payment"]["amount"])
print(Invoice.objects.get(pk=invoice.pk).status)
PY
```

Run the Epic 5 tests:

```bash
docker compose run --rm web pytest apps/accounting/tests/test_api_ingestion.py -v
```

## API Surface Included

- `POST /api/v1/invoices/`
- `POST /api/v1/bills/`
- `POST /api/v1/payments/`
- `POST /api/v1/credits/`
- `POST /api/v1/refunds/`

The endpoints use a hybrid contract: the path is resource-shaped, but the payload is still event-shaped.

## Notes

- Duplicate submissions return the full original success payload, not a reduced duplicate envelope.
- The API request record model stores the request hash, nonce, response payload, and resulting record identifiers so replays are stable.
- Refund submissions currently reuse the existing credit-memo service path. If the product later introduces a first-class refund model, it should preserve the same idempotency behavior.
- Bank events are deliberately deferred from Epic 5 MVP and are not part of the active manual checklist.
- The implementation follows the service-layer rule: API views validate and route requests, but posting logic stays in domain services.
