# LedgerOS User Manual

This manual is for technically competent users setting up and operating a minimum viable LedgerOS backend. It assumes Docker.

LedgerOS currently supports two client-interface patterns:

1. A transitional human interface through Django Admin for setup, inspection, and early internal testing.
2. A machine-facing API integration client for external systems submitting customers, vendors, invoices, bills, payments, credits, and refunds.

For production bookkeeping by a non-technical bookkeeper, the recommended path is a dedicated bookkeeper-facing UI built on top of the backend. Requirements for that UI are included below so an agent can implement it safely.

## 1. Quick start

```bash
cp .env.example .env
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml
docker compose run --rm web python manage.py createsuperuser
docker compose up web
```

Open:

- Admin: `http://localhost:8000/admin/`
- API: `http://localhost:8000/api/v1/`

Validate the project:

```bash
./scripts/check.sh
```

## 2. Plain-English system concepts

### Entity

An entity is the company/books being accounted for. The MVP uses one hidden default entity.

### Chart of accounts

Accounts classify financial activity. Examples: cash, accounts receivable, revenue, expenses, accounts payable, equity, and clearing accounts.

### Accounting period

A period controls whether entries can be posted for a date range. Period states are:

- `open`: postings are allowed.
- `closed`: postings are rejected.
- `locked`: postings are rejected.

### Journal entry

A journal entry is the double-entry accounting record. Drafts do not affect balances. Posted entries affect balances. Posted entries are not edited destructively; they are reversed.

### AR/AP records

Customers, vendors, invoices, bills, payments, and credits are operational records that create or reference posted journal entries.

### Bank records

Bank accounts, bank transactions, statement lines, reconciliations, and matches support bank-side workflows. Bank-feed API ingestion is deferred.

### Reports

Reports are read-side outputs built from posted accounting data and reporting services/selectors.

## 3. Minimum viable realistic entity setup

This section creates enough data to operate a small realistic company locally.

### 3.1 Start the system

```bash
cp .env.example .env
docker compose build
docker compose up -d db
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py import_coa config/sample_chart_of_accounts.yml
docker compose run --rm web python manage.py createsuperuser
docker compose up web
```

### 3.2 Create an accounting period

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import create_accounting_period

period = create_accounting_period(
    start_date=date(2026, 1, 1),
    end_date=date(2026, 12, 31),
    name="FY2026",
)

print(period.id, period.name, period.start_date, period.end_date, period.status)
PY
```

### 3.3 Confirm accounts exist

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.models import Account

for account in Account.objects.order_by("account_code"):
    print(account.account_code, account.name, account.account_type, account.normal_balance)
PY
```

If required operating accounts are missing, add them through Django Admin or update `config/sample_chart_of_accounts.yml` and re-import in a fresh local database.

### 3.4 Create a customer and vendor

Use Django Admin for early setup, or use a Django shell script. The exact account codes depend on the chart of accounts imported into your database.

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.models import Account, Customer, Vendor
from apps.accounting.services import get_default_entity

entity = get_default_entity()
ar = Account.objects.get(entity=entity, account_code="1100")
ap = Account.objects.get(entity=entity, account_code="2000")

customer, _ = Customer.objects.get_or_create(
    entity=entity,
    customer_code="ACME",
    defaults={"name": "Acme Customer", "default_ar_account": ar},
)

vendor, _ = Vendor.objects.get_or_create(
    entity=entity,
    vendor_code="OFFICEDEPOT",
    defaults={"name": "Office Depot", "default_ap_account": ap},
)

print("Customer:", customer.customer_code, customer.name)
print("Vendor:", vendor.vendor_code, vendor.name)
PY
```

If your imported chart uses different AR/AP account codes, adjust `1100` and `2000`.

### 3.5 Create and post an invoice

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, Customer, Invoice, InvoiceLine
from apps.accounting.services import get_default_entity, post_invoice

entity = get_default_entity()
customer = Customer.objects.get(entity=entity, customer_code="ACME")
revenue = Account.objects.get(entity=entity, account_code="4000")

invoice = Invoice.objects.create(
    entity=entity,
    customer=customer,
    invoice_number="INV-LOCAL-001",
    date=date(2026, 1, 15),
    due_date=date(2026, 2, 14),
    total_amount=Decimal("1000.00"),
)
InvoiceLine.objects.create(
    invoice=invoice,
    account=revenue,
    line_description="Consulting services",
    amount=Decimal("1000.00"),
)

journal_entry = post_invoice(invoice=invoice)
print("Invoice:", invoice.invoice_number, invoice.status)
print("Journal entry:", journal_entry.id, journal_entry.status)
PY
```

### 3.6 Record a customer payment

Customer payments currently use Undeposited Funds before bank deposit.

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Invoice, Payment
from apps.accounting.services import apply_payment_to_invoice, get_default_entity, get_or_create_undeposited_funds_account

entity = get_default_entity()
invoice = Invoice.objects.get(entity=entity, invoice_number="INV-LOCAL-001")
clearing = get_or_create_undeposited_funds_account(entity=entity)

payment = Payment.objects.create(
    entity=entity,
    source_type=Payment.SourceType.INVOICE,
    source_id=invoice.id,
    amount=Decimal("1000.00"),
    payment_date=date(2026, 1, 20),
    account=clearing,
)
application, journal_entry = apply_payment_to_invoice(
    payment=payment,
    invoice=invoice,
    applied_amount=Decimal("1000.00"),
)
print("Payment:", payment.id)
print("Application:", application.id)
print("Journal entry:", journal_entry.id, journal_entry.status)
PY
```

### 3.7 Create and post a bill

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Account, Bill, BillLine, Vendor
from apps.accounting.services import get_default_entity, post_bill

entity = get_default_entity()
vendor = Vendor.objects.get(entity=entity, vendor_code="OFFICEDEPOT")
expense = Account.objects.get(entity=entity, account_code="5000")

bill = Bill.objects.create(
    entity=entity,
    vendor=vendor,
    bill_number="BILL-LOCAL-001",
    date=date(2026, 1, 18),
    due_date=date(2026, 2, 17),
    total_amount=Decimal("250.00"),
)
BillLine.objects.create(
    bill=bill,
    account=expense,
    line_description="Office supplies",
    amount=Decimal("250.00"),
)

journal_entry = post_bill(bill=bill)
print("Bill:", bill.bill_number, bill.status)
print("Journal entry:", journal_entry.id, journal_entry.status)
PY
```

### 3.8 Record a vendor payment

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from decimal import Decimal
from apps.accounting.models import Bill, Payment
from apps.accounting.services import apply_payment_to_bill, get_default_entity, get_or_create_undeposited_funds_account

entity = get_default_entity()
bill = Bill.objects.get(entity=entity, bill_number="BILL-LOCAL-001")
clearing = get_or_create_undeposited_funds_account(entity=entity)

payment = Payment.objects.create(
    entity=entity,
    source_type=Payment.SourceType.BILL,
    source_id=bill.id,
    amount=Decimal("250.00"),
    payment_date=date(2026, 1, 25),
    account=clearing,
)
application, journal_entry = apply_payment_to_bill(
    payment=payment,
    bill=bill,
    applied_amount=Decimal("250.00"),
)
print("Payment:", payment.id)
print("Application:", application.id)
print("Journal entry:", journal_entry.id, journal_entry.status)
PY
```

### 3.9 Run reports

```bash
curl -u <username>:<password> "http://localhost:8000/api/v1/reports/profit_and_loss/?start_date=2026-01-01&end_date=2026-12-31&basis=accrual" | jq
curl -u <username>:<password> "http://localhost:8000/api/v1/reports/balance_sheet/?as_of=2026-12-31" | jq
```

## 4. Transitional admin usage

Django Admin is acceptable for:

- initial local setup,
- inspecting records,
- internal testing,
- debugging accounting flows,
- reviewing audit logs.

Django Admin is not the recommended long-term interface for non-technical bookkeeping. A bookkeeper-facing UI should be built for normal production entry.

Admin safety rules:

- Do not manually edit posted accounting facts.
- Do not directly change status fields to force workflow progress.
- Use service-backed actions when available.
- Prefer reversal/correction workflows over destructive edits.
- Treat audit logs as read-only.

## 5. Bookkeeper-facing client interface requirements

A production bookkeeper UI should be simple, safe, and workflow-driven. It should hide unnecessary accounting internals while preserving explicit accounting actions.

### Required screens

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
- Settings/reference data

### Required workflows

Customer side:

- Create/update customer.
- Create draft invoice.
- Add invoice lines.
- Post invoice.
- Record customer payment.
- Apply customer payment.
- Issue customer credit.
- View invoice outstanding balance.

Vendor side:

- Create/update vendor.
- Create draft bill.
- Add bill lines.
- Post bill.
- Record vendor payment.
- Apply vendor payment.
- Issue vendor credit.
- View bill outstanding balance.

Banking side:

- Create bank account.
- Record bank deposit or withdrawal.
- Create bank statement line.
- Match statement line to bank transaction.
- Complete reconciliation.

Reporting side:

- Run balance sheet as of a date.
- Run profit and loss for a date range.
- Drill down report totals.
- View tax summary.
- View period summary.

### UI safety rules

The UI must:

- Use explicit actions for posting, reversal, payment application, matching, and reconciliation completion.
- Prevent generic editing of posted invoices, bills, journal entries, payments, and reconciliations.
- Show statuses clearly: draft, posted, reversed, voided, open, closed, locked, completed.
- Display validation errors directly and plainly.
- Route all accounting mutations through backend services or service-backed API endpoints.
- Never write directly to status fields to bypass workflows.
- Never allow deleting posted accounting records.
- Show audit history for material actions.

### Agent prompt for building the bookkeeper UI

Use this prompt as a starting point for an implementation agent:

```text
Build a simple bookkeeper-facing web UI for LedgerOS.

The backend is a Django/DRF accounting system. Use the existing API and, where a needed endpoint is missing, add thin service-backed endpoints rather than bypassing services.

Prioritize safe data entry over flexibility.

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

Rules:
- Do not mutate posted accounting records directly.
- Do not expose raw status editing.
- Use explicit actions: Post, Reverse, Apply Payment, Issue Credit, Match, Complete Reconciliation.
- Show validation errors from the backend.
- Keep Django Admin available for technical setup, but do not rely on it as the bookkeeper UI.
- Add tests for every workflow that changes accounting state.
- Run Docker checks before handoff.

Before coding, read:
- docs/technical-spec.md
- docs/accounting-core-invariants.md
- docs/reporting-invariants.md
- docs/ai-agent-guidance.md
```

## 6. API integration client setup

The API integration client is for external systems that submit accounting events into LedgerOS.

Supported write endpoints:

```text
POST /api/v1/invoices/
POST /api/v1/bills/
POST /api/v1/payments/
POST /api/v1/credits/
POST /api/v1/refunds/
POST /api/v1/customers/
POST /api/v1/vendors/
```

These are resource-shaped endpoints with event-shaped behavior. Bank event ingestion is deferred from the MVP.

### 6.1 Configure API clients

The repo includes `api_clients.yml`:

```yaml
api_clients:
  - client_id: api_full
    enabled: true
    secret_env: LEDGEROS_API_CLIENT_FULL_SECRET
    scopes:
      - customers
      - vendors
      - invoices
      - bills
      - payments
      - sync_events
      - credits
    allowed_event_types:
      - customer.upsert_requested
      - vendor.upsert_requested
      - invoice.post_requested
      - bill.post_requested
      - payment.post_requested
      - sync.event_received
      - credit.post_requested
      - refund.post_requested
```

Set the config path and secret:

```bash
LEDGEROS_API_CLIENTS_CONFIG=/app/api_clients.yml
LEDGEROS_API_CLIENT_FULL_SECRET=replace-this-with-a-local-secret
```

In Docker Compose, `/app/api_clients.yml` refers to the file inside the container.

### 6.2 Required HMAC headers

Write requests use HMAC authentication. Headers:

```text
X-LedgerOS-Client-Id: api_full
X-LedgerOS-Timestamp: <unix timestamp seconds>
X-LedgerOS-Nonce: <unique nonce per client>
X-LedgerOS-Signature: <hex hmac sha256 signature>
Idempotency-Key: <stable unique key for this business request>
Content-Type: application/json
```

The canonical signature input is:

```text
client_id + "\n" + METHOD + "\n" + PATH + "\n" + TIMESTAMP + "\n" + NONCE + "\n" + SHA256_HEX(CANONICAL_JSON_BODY)
```

The body is canonicalized as JSON with sorted keys and compact separators before hashing.

### 6.3 Idempotency behavior

Every write request needs an idempotency key.

- First accepted request creates the accounting result.
- A repeated request with the same client, event type, entity, idempotency key, and same payload returns the original success payload.
- Reusing the same key with a different payload is rejected.
- Reusing a nonce is rejected.

### 6.4 Example invoice payload

```json
{
  "customer_code": "ACME",
  "external_invoice_number": "EXT-INV-1001",
  "invoice_date": "2026-01-15",
  "due_date": "2026-02-14",
  "total_amount": "1000.00",
  "lines": [
    {
      "account_code": "4000",
      "line_description": "Consulting services",
      "amount": "1000.00"
    }
  ]
}
```

### 6.5 Example bill payload

```json
{
  "vendor_code": "OFFICEDEPOT",
  "external_bill_number": "EXT-BILL-2001",
  "bill_date": "2026-01-18",
  "due_date": "2026-02-17",
  "total_amount": "250.00",
  "lines": [
    {
      "account_code": "5000",
      "line_description": "Office supplies",
      "amount": "250.00"
    }
  ]
}
```

### 6.6 Example vendor payload

```json
{
  "vendor_code": "OFFICEDEPOT",
  "name": "Office Depot",
  "default_ap_account_code": "2100",
  "status": "active"
}
```

### 6.7 Example payment payload

```json
{
  "source_type": "invoice",
  "source_reference": "EXT-INV-1001",
  "payment_date": "2026-01-20",
  "amount": "1000.00"
}
```

For vendor payments, use:

```json
{
  "source_type": "bill",
  "source_reference": "EXT-BILL-2001",
  "payment_date": "2026-01-25",
  "amount": "250.00"
}
```

### 6.8 Example credit/refund payload

```json
{
  "source_type": "invoice",
  "source_reference": "EXT-INV-1001",
  "credit_date": "2026-01-21",
  "amount": "100.00",
  "reason": "Customer credit"
}
```

### 6.9 Real Python HMAC example

```python
import hashlib
import hmac
import json
import time
import uuid

import requests

BASE_URL = "http://localhost:8000"
CLIENT_ID = "api_full"
SECRET = "replace-this-with-a-local-secret"


def canonical_body(payload: dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def sign_request(method: str, path: str, payload: dict, nonce: str, timestamp: str) -> str:
    body = canonical_body(payload)
    body_hash = hashlib.sha256(body).hexdigest()
    signing_payload = "\n".join([
        CLIENT_ID,
        method.upper(),
        path,
        timestamp,
        nonce,
        body_hash,
    ]).encode("utf-8")
    return hmac.new(SECRET.encode("utf-8"), signing_payload, hashlib.sha256).hexdigest()


def post_invoice():
    path = "/api/v1/invoices/"
    payload = {
        "customer_code": "ACME",
        "external_invoice_number": "EXT-INV-1001",
        "invoice_date": "2026-01-15",
        "due_date": "2026-02-14",
        "total_amount": "1000.00",
        "lines": [
            {
                "account_code": "4000",
                "line_description": "Consulting services",
                "amount": "1000.00",
            }
        ],
    }
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    signature = sign_request("POST", path, payload, nonce, timestamp)
    response = requests.post(
        BASE_URL + path,
        data=canonical_body(payload),
        headers={
            "Content-Type": "application/json",
            "X-LedgerOS-Client-Id": CLIENT_ID,
            "X-LedgerOS-Timestamp": timestamp,
            "X-LedgerOS-Nonce": nonce,
            "X-LedgerOS-Signature": signature,
            "Idempotency-Key": "invoice-EXT-INV-1001-v1",
        },
        timeout=30,
    )
    print(response.status_code)
    print(response.json())


if __name__ == "__main__":
    post_invoice()
```

### 6.10 Agent prompt for building an API client

```text
Build a LedgerOS API integration client.

The client must submit customers, vendors, invoices, bills, payments, credits, and refunds to LedgerOS using the Epic 5 API.

Requirements:
- Read API credentials from environment variables or a secrets manager.
- Never hard-code secrets.
- Sign every write request with LedgerOS HMAC headers.
- Generate a unique nonce per request.
- Generate stable idempotency keys per business operation.
- Retry safely on network failure using the same idempotency key but a new nonce.
- Treat duplicate/idempotent success responses as success.
- Surface validation errors clearly to the operator.
- Log request IDs, endpoint names, external references, and response codes, but never log secrets or HMAC signatures.
- Include tests for signature generation and idempotency retry behavior.

Supported endpoints:
- POST /api/v1/customers/
- POST /api/v1/vendors/
- POST /api/v1/invoices/
- POST /api/v1/bills/
- POST /api/v1/payments/
- POST /api/v1/credits/
- POST /api/v1/refunds/

Before coding, read:
- docs/api-auth-idempotency.md
- docs/api-client-config-schema.md
- docs/epic-05-api-contract.md
- docs/technical-spec.md
```

## 7. Daily operating workflows

### Invoice workflow

1. Create customer.
2. Create draft invoice.
3. Add invoice lines.
4. Post invoice.
5. Record and apply payment.
6. Issue credit only when needed.
7. Review outstanding balance.

### Bill workflow

1. Create vendor.
2. Create draft bill.
3. Add bill lines.
4. Post bill.
5. Record and apply vendor payment.
6. Issue vendor credit only when needed.
7. Review outstanding balance.

### Correction workflow

Use reversal or credit workflows. Do not destructively edit posted accounting records.

### Period close workflow

1. Confirm postings are complete.
2. Run trial balance and reports.
3. Resolve exceptions.
4. Move the period to `closed`.
5. Use `locked` only when the period should reject all further postings.

## 8. Troubleshooting

### Migrations fail

Run:

```bash
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py showmigrations
```

### Account code not found

Confirm the chart of accounts was imported and that the account code exists:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.models import Account
print(list(Account.objects.values_list("account_code", "name")))
PY
```

### Posting rejected because period is closed or locked

Create or reopen the correct period in a controlled test environment. Do not bypass period validation in production data.

### API request rejected for HMAC

Check:

- `X-LedgerOS-Client-Id`
- timestamp skew
- nonce uniqueness
- exact request path including trailing slash
- canonical JSON body
- secret environment variable inside the Docker container

### Duplicate API request rejected

Use the same idempotency key only for the same business payload. Use a new nonce on retries.
