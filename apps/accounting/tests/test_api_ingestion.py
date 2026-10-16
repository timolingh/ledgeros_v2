from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounting.models import ApiRequestRecord, Account, BankAccount, BankReconciliation, BankTransaction, Bill, Customer, Entity, Invoice, JournalEntry, Payment, SyncEventRecord, Vendor
from apps.accounting.services import create_accounting_period
from apps.accounting.services.chart_import import import_chart_of_accounts
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.banking import create_bank_reconciliation


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def api_ingestion_ready(tmp_path, monkeypatch):
    entity = get_default_entity()
    path = tmp_path / "coa.yml"
    path.write_text(
        """accounts:
  - code: "1000"
    name: Cash
    type: asset
    normal_balance: debit
  - code: "1010"
    name: Undeposited Funds
    type: asset
    normal_balance: debit
  - code: "1100"
    name: Accounts Receivable
    type: asset
    normal_balance: debit
  - code: "2100"
    name: Accounts Payable
    type: liability
    normal_balance: credit
  - code: "4000"
    name: Revenue
    type: revenue
    normal_balance: credit
  - code: "5000"
    name: Operating Expense
    type: expense
    normal_balance: debit
""",
        encoding="utf-8",
    )
    import_chart_of_accounts(path=path, entity=entity)
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")

    ar = Account.objects.get(entity=entity, account_code="1100")
    ap = Account.objects.get(entity=entity, account_code="2100")

    customer = Customer.objects.create(
        entity=entity,
        name="API Ingestion Customer",
        customer_code="API-CUST-001",
        default_ar_account=ar,
    )
    vendor = Vendor.objects.create(
        entity=entity,
        name="API Ingestion Vendor",
        vendor_code="API-VEND-001",
        default_ap_account=ap,
    )

    monkeypatch.setenv("LEDGEROS_API_CLIENT_FULL_SECRET", "full-secret")
    monkeypatch.setenv("LEDGEROS_API_CLIENT_INVOICE_ONLY_SECRET", "invoice-secret")
    config_path = tmp_path / "api_clients.yml"
    config_path.write_text(
        """api_clients:
  - client_id: api_full
    enabled: true
    secret_env: LEDGEROS_API_CLIENT_FULL_SECRET
    scopes:
      - customers
      - vendors
      - invoices
      - bills
      - payments
      - banking
      - sync_events
      - credits
    allowed_event_types:
      - customer.upsert_requested
      - vendor.upsert_requested
      - invoice.post_requested
      - bill.post_requested
      - payment.post_requested
      - bank.deposit_requested
      - bank.withdrawal_requested
      - sync.event_received
      - credit.post_requested
      - refund.post_requested
  - client_id: api_invoice_only
    enabled: true
    secret_env: LEDGEROS_API_CLIENT_INVOICE_ONLY_SECRET
    scopes:
      - invoices
    allowed_event_types:
      - invoice.post_requested
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("LEDGEROS_API_CLIENTS_CONFIG", str(config_path))

    return {
        "entity": entity,
        "customer": customer,
        "vendor": vendor,
        "clients": {
            "api_full": "full-secret",
            "api_invoice_only": "invoice-secret",
        },
    }


def _signed_headers(
    *,
    client_id: str,
    secret: str,
    path: str,
    payload: dict | None = None,
    idempotency_key: str | None = None,
    nonce: str | None = None,
    method: str = "POST",
) -> dict[str, str]:
    nonce = nonce or (f"nonce-{idempotency_key}" if idempotency_key is not None else "nonce-read")
    body = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        if payload is not None
        else b""
    )
    body_hash = hashlib.sha256(body).hexdigest()
    timestamp = str(int(time.time()))
    message = "\n".join([client_id, method.upper(), path, timestamp, nonce, body_hash]).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    headers = {
        "HTTP_X_LEDGEROS_CLIENT_ID": client_id,
        "HTTP_X_LEDGEROS_TIMESTAMP": timestamp,
        "HTTP_X_LEDGEROS_NONCE": nonce,
        "HTTP_X_LEDGEROS_SIGNATURE": signature,
    }
    if idempotency_key is not None:
        headers["HTTP_IDEMPOTENCY_KEY"] = idempotency_key
    return headers


@pytest.mark.django_db
def test_invoice_submission_is_idempotent(api_client, api_ingestion_ready):
    payload = {
        "customer_code": "API-CUST-001",
        "external_invoice_number": "EXT-INV-001",
        "invoice_date": "2026-05-01",
        "due_date": "2026-06-01",
        "total_amount": "100.00",
        "lines": [
            {"account_code": "4000", "line_description": "Revenue", "amount": "100.00"},
        ],
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/invoices/",
        payload=payload,
        idempotency_key="invoice-001",
    )

    first = api_client.post("/api/v1/invoices/", payload, format="json", **headers)
    second = api_client.post("/api/v1/invoices/", payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data == second.data
    assert first.data["invoice"]["external_invoice_number"] == "EXT-INV-001"
    assert first.data["invoice"]["external_source_client_id"] == "api_full"
    assert Invoice.objects.get(external_source_client_id="api_full", external_invoice_number="EXT-INV-001").status == Invoice.Status.POSTED
    assert ApiRequestRecord.objects.filter(client_id="api_full", event_type="invoice.post_requested").count() == 1


@pytest.mark.django_db
def test_customer_submission_is_idempotent(api_client, api_ingestion_ready):
    payload = {
        "customer_code": "CUST-001",
        "name": "Tenant One",
        "default_ar_account_code": "1100",
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/customers/",
        payload=payload,
        idempotency_key="customer-001",
    )

    first = api_client.post("/api/v1/customers/", payload, format="json", **headers)
    second = api_client.post("/api/v1/customers/", payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data == second.data
    assert first.data["customer"]["customer_code"] == "CUST-001"
    assert first.data["customer"]["default_ar_account_code"] == "1100"
    assert Customer.objects.filter(customer_code="CUST-001").count() == 1
    assert ApiRequestRecord.objects.filter(client_id="api_full", event_type="customer.upsert_requested").count() == 1


@pytest.mark.django_db
def test_vendor_submission_is_idempotent(api_client, api_ingestion_ready):
    payload = {
        "vendor_code": "VEND-001",
        "name": "Supplier One",
        "default_ap_account_code": "2100",
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/vendors/",
        payload=payload,
        idempotency_key="vendor-001",
    )

    first = api_client.post("/api/v1/vendors/", payload, format="json", **headers)
    second = api_client.post("/api/v1/vendors/", payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data == second.data
    assert first.data["vendor"]["vendor_code"] == "VEND-001"
    assert first.data["vendor"]["default_ap_account_code"] == "2100"
    assert Vendor.objects.filter(vendor_code="VEND-001").count() == 1
    assert ApiRequestRecord.objects.filter(client_id="api_full", event_type="vendor.upsert_requested").count() == 1


@pytest.mark.django_db
def test_vendor_upsert_updates_existing_vendor_by_code(api_client, api_ingestion_ready):
    create_payload = {
        "vendor_code": "VEND-UPDATE",
        "name": "Original Supplier",
        "default_ap_account_code": "2100",
    }
    create_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/vendors/",
        payload=create_payload,
        idempotency_key="vendor-update-001",
    )
    create_response = api_client.post("/api/v1/vendors/", create_payload, format="json", **create_headers)
    assert create_response.status_code == 201

    update_payload = {
        "vendor_code": "VEND-UPDATE",
        "name": "Updated Supplier",
    }
    update_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/vendors/",
        payload=update_payload,
        idempotency_key="vendor-update-002",
    )
    update_response = api_client.post("/api/v1/vendors/", update_payload, format="json", **update_headers)

    assert update_response.status_code == 200
    assert update_response.data["vendor"]["name"] == "Updated Supplier"
    vendor = Vendor.objects.get(vendor_code="VEND-UPDATE")
    assert vendor.name == "Updated Supplier"
    assert vendor.default_ap_account.account_code == "2100"


@pytest.mark.django_db
def test_customer_upsert_updates_existing_customer_by_code(api_client, api_ingestion_ready):
    create_payload = {
        "customer_code": "CUST-UPDATE",
        "name": "Original Tenant",
        "default_ar_account_code": "1100",
    }
    create_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/customers/",
        payload=create_payload,
        idempotency_key="customer-update-001",
    )
    create_response = api_client.post("/api/v1/customers/", create_payload, format="json", **create_headers)
    assert create_response.status_code == 201

    update_payload = {
        "customer_code": "CUST-UPDATE",
        "name": "Updated Tenant",
    }
    update_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/customers/",
        payload=update_payload,
        idempotency_key="customer-update-002",
    )
    update_response = api_client.post("/api/v1/customers/", update_payload, format="json", **update_headers)

    assert update_response.status_code == 200
    assert update_response.data["customer"]["name"] == "Updated Tenant"
    customer = Customer.objects.get(customer_code="CUST-UPDATE")
    assert customer.name == "Updated Tenant"
    assert customer.default_ar_account.account_code == "1100"


@pytest.mark.django_db
def test_same_external_invoice_number_is_allowed_for_different_clients(api_client, api_ingestion_ready):
    payload = {
        "customer_code": "API-CUST-001",
        "external_invoice_number": "EXT-SHARED-001",
        "invoice_date": "2026-05-02",
        "due_date": "2026-06-02",
        "total_amount": "50.00",
        "lines": [
            {"account_code": "4000", "line_description": "Revenue", "amount": "50.00"},
        ],
    }
    headers_one = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/invoices/",
        payload=payload,
        idempotency_key="invoice-shared-1",
    )
    headers_two = _signed_headers(
        client_id="api_invoice_only",
        secret=api_ingestion_ready["clients"]["api_invoice_only"],
        path="/api/v1/invoices/",
        payload=payload,
        idempotency_key="invoice-shared-2",
    )

    first = api_client.post("/api/v1/invoices/", payload, format="json", **headers_one)
    second = api_client.post("/api/v1/invoices/", payload, format="json", **headers_two)

    assert first.status_code == 201
    assert second.status_code == 201
    assert Invoice.objects.filter(external_invoice_number="EXT-SHARED-001").count() == 2


@pytest.mark.django_db
def test_payment_submission_posts_and_reduces_balance(api_client, api_ingestion_ready):
    invoice_payload = {
        "customer_code": "API-CUST-001",
        "external_invoice_number": "EXT-PAY-001",
        "invoice_date": "2026-05-03",
        "due_date": "2026-06-03",
        "total_amount": "75.00",
        "lines": [
            {"account_code": "4000", "line_description": "Revenue", "amount": "75.00"},
        ],
    }
    invoice_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/invoices/",
        payload=invoice_payload,
        idempotency_key="invoice-pay-001",
    )
    invoice_response = api_client.post("/api/v1/invoices/", invoice_payload, format="json", **invoice_headers)
    assert invoice_response.status_code == 201

    payment_payload = {
        "source_type": "invoice",
        "source_reference": "EXT-PAY-001",
        "payment_date": "2026-05-10",
        "amount": "75.00",
    }
    payment_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/payments/",
        payload=payment_payload,
        idempotency_key="payment-001",
    )
    payment_response = api_client.post("/api/v1/payments/", payment_payload, format="json", **payment_headers)

    invoice = Invoice.objects.get(external_source_client_id="api_full", external_invoice_number="EXT-PAY-001")
    payment = Payment.objects.get(source_type=Payment.SourceType.INVOICE, source_id=invoice.id)
    assert payment_response.status_code == 201
    assert payment_response.data["payment"]["amount"] == "75.00"
    assert payment_response.data["journal_entry"]["status"] == "posted"
    assert payment.account.account_code == "1000"
    assert payment.account.name == "Cash"
    assert invoice.status == Invoice.Status.PAID
    assert invoice.outstanding_balance() == Decimal("0.00")


@pytest.mark.django_db
def test_bank_account_listing_exposes_current_balance(api_client, api_ingestion_ready):
    entity = api_ingestion_ready["entity"]
    cash_account = Account.objects.get(entity=entity, account_code="1000")
    bank_account = BankAccount.objects.create(
        entity=entity,
        name="Operating Checking",
        account_number="1111",
        bank_name="First Bank",
        ledger_account=cash_account,
    )

    deposit_payload = {
        "bank_account_id": bank_account.id,
        "transaction_date": "2026-05-15",
        "amount": "150.00",
        "offset_account_code": "4000",
        "memo": "Deposit",
    }
    deposit_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bank-deposits/",
        payload=deposit_payload,
        idempotency_key="bank-deposit-001",
    )
    deposit_response = api_client.post("/api/v1/bank-deposits/", deposit_payload, format="json", **deposit_headers)
    assert deposit_response.status_code == 201

    list_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bank-accounts/",
        method="GET",
    )
    list_response = api_client.get("/api/v1/bank-accounts/", **list_headers)

    assert list_response.status_code == 200
    assert len(list_response.data) == 1
    assert list_response.data[0]["name"] == "Operating Checking"
    assert list_response.data[0]["ledger_account_code"] == "1000"
    assert list_response.data[0]["current_balance"] == "150.00"


@pytest.mark.django_db
def test_bank_deposit_submission_posts_bank_transaction(api_client, api_ingestion_ready):
    entity = api_ingestion_ready["entity"]
    cash_account = Account.objects.get(entity=entity, account_code="1000")
    bank_account = BankAccount.objects.create(
        entity=entity,
        name="Deposit Checking",
        account_number="2222",
        bank_name="Second Bank",
        ledger_account=cash_account,
    )

    payload = {
        "bank_account_id": bank_account.id,
        "transaction_date": "2026-05-16",
        "amount": "40.00",
        "offset_account_code": "5000",
        "memo": "Bank fee reimbursement",
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bank-deposits/",
        payload=payload,
        idempotency_key="bank-deposit-002",
    )

    first = api_client.post("/api/v1/bank-deposits/", payload, format="json", **headers)
    second = api_client.post("/api/v1/bank-deposits/", payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data == second.data
    assert first.data["bank_transaction"]["transaction_type"] == BankTransaction.Type.DEPOSIT
    assert first.data["journal_entry"]["status"] == JournalEntry.Status.POSTED
    assert BankAccount.objects.get(pk=bank_account.pk).current_balance() == Decimal("40.00")
    assert ApiRequestRecord.objects.filter(client_id="api_full", event_type="bank.deposit_requested").count() == 1


@pytest.mark.django_db
def test_bank_withdrawal_submission_posts_bank_transaction(api_client, api_ingestion_ready):
    entity = api_ingestion_ready["entity"]
    cash_account = Account.objects.get(entity=entity, account_code="1000")
    bank_account = BankAccount.objects.create(
        entity=entity,
        name="Withdrawal Checking",
        account_number="3333",
        bank_name="Third Bank",
        ledger_account=cash_account,
    )

    payload = {
        "bank_account_id": bank_account.id,
        "transaction_date": "2026-05-17",
        "amount": "25.00",
        "offset_account_code": "5000",
        "memo": "ATM fee",
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bank-withdrawals/",
        payload=payload,
        idempotency_key="bank-withdrawal-001",
    )

    response = api_client.post("/api/v1/bank-withdrawals/", payload, format="json", **headers)

    assert response.status_code == 201
    assert response.data["bank_transaction"]["transaction_type"] == BankTransaction.Type.WITHDRAWAL
    assert response.data["journal_entry"]["status"] == JournalEntry.Status.POSTED
    assert BankAccount.objects.get(pk=bank_account.pk).current_balance() == Decimal("-25.00")
    assert ApiRequestRecord.objects.filter(client_id="api_full", event_type="bank.withdrawal_requested").count() == 1


@pytest.mark.django_db
def test_bank_reconciliation_listing_exposes_status(api_client, api_ingestion_ready):
    entity = api_ingestion_ready["entity"]
    cash_account = Account.objects.get(entity=entity, account_code="1000")
    bank_account = BankAccount.objects.create(
        entity=entity,
        name="Recon Checking",
        account_number="4444",
        bank_name="Fourth Bank",
        ledger_account=cash_account,
    )
    deposit_payload = {
        "bank_account_id": bank_account.id,
        "transaction_date": "2026-05-18",
        "amount": "60.00",
        "offset_account_code": "4000",
        "memo": "Deposit",
    }
    deposit_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bank-deposits/",
        payload=deposit_payload,
        idempotency_key="bank-deposit-003",
    )
    assert api_client.post("/api/v1/bank-deposits/", deposit_payload, format="json", **deposit_headers).status_code == 201

    reconciliation = create_bank_reconciliation(
        bank_account=bank_account,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        statement_ending_balance=Decimal("60.00"),
    )
    list_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bank-reconciliations/",
        method="GET",
    )
    list_response = api_client.get("/api/v1/bank-reconciliations/", **list_headers)

    assert list_response.status_code == 200
    assert list_response.data[0]["id"] == reconciliation.id
    assert list_response.data[0]["status"] == BankReconciliation.Status.OPEN
    assert list_response.data[0]["book_balance"] == "60.00"


@pytest.mark.django_db
def test_sync_event_submission_is_idempotent(api_client, api_ingestion_ready):
    payload = {
        "source_system": "propertyledger",
        "domain_event_type": "security_deposit.received",
        "external_id": "prop-1:secdep:1",
        "source_object_type": "security_deposit_event",
        "source_object_id": "1",
        "occurred_at": "2026-05-17T12:00:00Z",
        "payload": {
            "property_id": 1,
            "tenant_id": 2,
            "amount": "500.00",
            "description": "Security deposit received",
        },
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/sync-events/",
        payload=payload,
        idempotency_key="sync-event-001",
    )

    first = api_client.post("/api/v1/sync-events/", payload, format="json", **headers)
    second = api_client.post("/api/v1/sync-events/", payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data == second.data
    assert first.data["sync_event"]["external_id"] == "prop-1:secdep:1"
    assert SyncEventRecord.objects.filter(external_id="prop-1:secdep:1").count() == 1
    assert ApiRequestRecord.objects.filter(client_id="api_full", event_type="sync.event_received").count() == 1


@pytest.mark.django_db
def test_sync_event_submission_posts_balanced_journal_entry(api_client, api_ingestion_ready):
    payload = {
        "source_system": "propertyledger",
        "domain_event_type": "vendor_payment.credit_card",
        "external_id": "prop-1:vendpay:1",
        "source_object_type": "vendor_payment",
        "source_object_id": "1",
        "occurred_at": "2026-05-17T12:00:00Z",
        "payload": {
            "accounting_entries": [
                {"account_code": "2100", "direction": "debit", "amount": "125.00"},
                {"account_code": "1000", "direction": "credit", "amount": "125.00"},
            ],
        },
    }
    headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/sync-events/",
        payload=payload,
        idempotency_key="sync-event-002",
    )

    first = api_client.post("/api/v1/sync-events/", payload, format="json", **headers)
    second = api_client.post("/api/v1/sync-events/", payload, format="json", **headers)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.data == second.data
    assert first.data["journal_entry"]["status"] == JournalEntry.Status.POSTED
    assert JournalEntry.objects.filter(source="api", description="vendor_payment.credit_card").count() == 1
    journal_entry = JournalEntry.objects.get(source="api", description="vendor_payment.credit_card")
    assert list(journal_entry.lines.values_list("account__account_code", "side", "amount")) == [
        ("2100", "debit", Decimal("125.00")),
        ("1000", "credit", Decimal("125.00")),
    ]


@pytest.mark.django_db
def test_credit_and_refund_submissions_create_credit_memos(api_client, api_ingestion_ready):
    bill_payload = {
        "vendor_code": "API-VEND-001",
        "external_bill_number": "EXT-BILL-001",
        "bill_date": "2026-05-04",
        "due_date": "2026-06-04",
        "total_amount": "120.00",
        "lines": [
            {"account_code": "5000", "line_description": "Expense", "amount": "120.00"},
        ],
    }
    bill_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bills/",
        payload=bill_payload,
        idempotency_key="bill-001",
    )
    bill_response = api_client.post("/api/v1/bills/", bill_payload, format="json", **bill_headers)
    assert bill_response.status_code == 201

    credit_payload = {
        "source_type": "bill",
        "source_reference": "EXT-BILL-001",
        "credit_date": "2026-05-11",
        "amount": "20.00",
        "reason": "Vendor rebate",
    }
    credit_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/credits/",
        payload=credit_payload,
        idempotency_key="credit-001",
    )
    credit_response = api_client.post("/api/v1/credits/", credit_payload, format="json", **credit_headers)

    refund_payload = {
        "source_type": "bill",
        "source_reference": "EXT-BILL-001",
        "credit_date": "2026-05-12",
        "amount": "10.00",
        "reason": "Customer refund",
    }
    refund_headers = _signed_headers(
        client_id="api_full",
        secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/refunds/",
        payload=refund_payload,
        idempotency_key="refund-001",
    )
    refund_response = api_client.post("/api/v1/refunds/", refund_payload, format="json", **refund_headers)

    assert credit_response.status_code == 201
    assert credit_response.data["credit_memo"]["type"] == "vendor"
    assert refund_response.status_code == 201
    assert refund_response.data["event_type"] == "refund.post_requested"
    assert Bill.objects.get(external_source_client_id="api_full", external_bill_number="EXT-BILL-001").status in {Bill.Status.POSTED, Bill.Status.PARTIALLY_PAID, Bill.Status.PAID}


@pytest.mark.django_db
def test_client_scope_is_enforced(api_client, api_ingestion_ready):
    payload = {
        "customer_code": "API-CUST-001",
        "external_invoice_number": "EXT-SCOPE-001",
        "invoice_date": "2026-05-13",
        "due_date": "2026-06-13",
        "total_amount": "30.00",
        "lines": [
            {"account_code": "4000", "line_description": "Revenue", "amount": "30.00"},
        ],
    }
    headers = _signed_headers(
        client_id="api_invoice_only",
        secret=api_ingestion_ready["clients"]["api_invoice_only"],
        path="/api/v1/payments/",
        payload={
            "source_type": "invoice",
            "source_reference": "EXT-SCOPE-001",
            "payment_date": "2026-05-14",
            "amount": "30.00",
        },
        idempotency_key="payment-scope-001",
    )

    response = api_client.post(
        "/api/v1/payments/",
        {"source_type": "invoice", "source_reference": "EXT-SCOPE-001", "payment_date": "2026-05-14", "amount": "30.00"},
        format="json",
        **headers,
    )

    assert response.status_code == 403


@pytest.fixture
def settlement_bill(api_client, api_ingestion_ready):
    payload = {"vendor_code": "API-VEND-001", "external_bill_number": "BILL-SETTLE",
               "bill_date": "2026-05-01", "due_date": "2026-05-31", "total_amount": "100.00",
               "lines": [{"account_code": "5000", "amount": "100.00"}]}
    response = api_client.post("/api/v1/bills/", payload, format="json", **_signed_headers(
        client_id="api_full", secret="full-secret", path="/api/v1/bills/", payload=payload, idempotency_key="settlement-bill"))
    assert response.status_code == 201
    return Bill.objects.get(external_bill_number="BILL-SETTLE")


@pytest.mark.django_db
def test_bill_status_read_includes_external_payment_and_credit(api_client, api_ingestion_ready, settlement_bill):
    from apps.accounting.services.api_ingestion import submit_payment_event, submit_credit_event
    submit_payment_event(client_id="api_full", idempotency_key="external-payment", nonce="ext-pay", payload={
        "source_type": "bill", "source_reference": "BILL-SETTLE", "payment_date": date(2026, 5, 2), "amount": Decimal("40.00")})
    submit_credit_event(client_id="api_full", idempotency_key="external-credit", nonce="ext-credit", payload={
        "source_type": "bill", "source_reference": "BILL-SETTLE", "credit_date": date(2026, 5, 3), "amount": Decimal("10.00"), "reason": "Return"})
    before = JournalEntry.objects.count()
    response = api_client.get("/api/v1/bills/", {"external_bill_number": "BILL-SETTLE"}, **_signed_headers(
        client_id="api_full", secret="full-secret", path="/api/v1/bills/", method="GET"))
    assert response.status_code == 200
    row = response.data["results"][0]
    assert row["payment_status"] == "partially_paid"
    assert row["amount_paid"] == "40.00"
    assert row["amount_credited"] == "10.00"
    assert row["outstanding_balance"] == "50.00"
    assert JournalEntry.objects.count() == before


@pytest.mark.django_db
def test_bill_read_requires_scope_and_hides_other_client_bills(api_client, api_ingestion_ready, settlement_bill):
    response = api_client.get("/api/v1/bills/", {"external_bill_number": "BILL-SETTLE"}, **_signed_headers(
        client_id="api_invoice_only", secret="invoice-secret", path="/api/v1/bills/", method="GET"))
    assert response.status_code == 403
    settlement_bill.external_source_client_id = "different-client"
    settlement_bill.save()
    response = api_client.get("/api/v1/bills/", {"external_bill_number": "BILL-SETTLE"}, **_signed_headers(
        client_id="api_full", secret="full-secret", path="/api/v1/bills/", method="GET"))
    assert response.status_code == 200
    assert response.data["results"] == []


@pytest.mark.django_db
def test_card_bill_payment_posts_and_retries_without_duplicate(api_ingestion_ready, settlement_bill):
    from apps.accounting.services.api_ingestion import submit_payment_event
    card = Account.objects.create(entity=settlement_bill.entity, account_code="2200", name="Card", type="liability", normal_balance="credit")
    payload = {"source_type": "bill", "source_reference": "BILL-SETTLE", "payment_date": date(2026, 5, 2),
               "amount": Decimal("100.00"), "funding_account_code": "2200"}
    _, result = submit_payment_event(client_id="api_full", idempotency_key="card-payment", nonce="card-1", payload=payload)
    before = JournalEntry.objects.count()
    _, replay = submit_payment_event(client_id="api_full", idempotency_key="card-payment", nonce="card-2", payload=payload)
    settlement_bill.refresh_from_db()
    assert replay == result
    assert settlement_bill.outstanding_balance() == Decimal("0.00")
    assert settlement_bill.status == Bill.Status.PAID
    assert JournalEntry.objects.count() == before
    entry = JournalEntry.objects.get(pk=result["journal_entry"]["id"])
    assert entry.lines.get(side="credit").account_id == card.pk
    assert entry.lines.get(side="debit").account_id == settlement_bill.vendor.default_ap_account_id
    assert settlement_bill.payment_applications.get().journal_entry_id == entry.pk
    from apps.accounting.selectors import account_balance
    assert account_balance(card) == Decimal("100.00")
    assert account_balance(settlement_bill.vendor.default_ap_account) == Decimal("0.00")
    assert account_balance(Account.objects.get(entity=settlement_bill.entity, account_code="1000")) == Decimal("0.00")


@pytest.mark.django_db
def test_existing_card_event_links_once_without_reposting(api_ingestion_ready, settlement_bill):
    from django.core.exceptions import ValidationError
    from apps.accounting.services.api_ingestion import submit_sync_event, submit_payment_event
    Account.objects.create(entity=settlement_bill.entity, account_code="2200", name="Card", type="liability", normal_balance="credit")
    _, old = submit_sync_event(client_id="api_full", idempotency_key="old-card", nonce="old-card", payload={
        "source_system": "client", "domain_event_type": "card_payment", "external_id": "old-card",
        "source_object_type": "payment", "source_object_id": "1", "occurred_at": datetime(2026, 5, 2, tzinfo=timezone.utc),
        "payload": {"accounting_entries": [{"account_code": "2100", "direction": "debit", "amount": "100.00"},
                                           {"account_code": "2200", "direction": "credit", "amount": "100.00"}]}})
    before = JournalEntry.objects.count()
    payload = {"source_type": "bill", "source_reference": "BILL-SETTLE", "payment_date": date(2026, 5, 2),
               "amount": Decimal("100.00"), "funding_account_code": "2200", "existing_sync_event_id": old["sync_event"]["id"]}
    _, result = submit_payment_event(client_id="api_full", idempotency_key="link-card", nonce="link-card", payload=payload)
    assert result["journal_entry"]["id"] == old["journal_entry"]["id"]
    assert settlement_bill.outstanding_balance() == Decimal("0.00")
    assert JournalEntry.objects.count() == before
    with pytest.raises(ValidationError):
        submit_payment_event(client_id="api_full", idempotency_key="link-again", nonce="link-again", payload=payload)
    assert JournalEntry.objects.count() == before


@pytest.mark.django_db
@pytest.mark.parametrize("problem", ["amount", "funding", "owner", "reversed"])
def test_link_existing_event_rejects_mismatches_without_posting(api_ingestion_ready, settlement_bill, problem):
    from django.core.exceptions import ValidationError
    from apps.accounting.services.api_ingestion import submit_sync_event, submit_payment_event
    from apps.accounting.services import reverse_journal_entry
    Account.objects.create(entity=settlement_bill.entity, account_code="2200", name="Card", type="liability", normal_balance="credit")
    _, old = submit_sync_event(client_id="api_full", idempotency_key="legacy-test", nonce="legacy-test", payload={
        "source_system": "client", "domain_event_type": "card_payment", "external_id": "legacy-test",
        "source_object_type": "payment", "source_object_id": "1", "occurred_at": datetime(2026, 5, 2, tzinfo=timezone.utc),
        "payload": {"accounting_entries": [{"account_code": "2100", "direction": "debit", "amount": "100.00"},
                                           {"account_code": "2200", "direction": "credit", "amount": "100.00"}]}})
    payload = {"source_type": "bill", "source_reference": "BILL-SETTLE", "payment_date": date(2026, 5, 2),
               "amount": Decimal("100.00"), "funding_account_code": "2200", "existing_sync_event_id": old["sync_event"]["id"]}
    if problem == "amount":
        payload["amount"] = Decimal("90.00")
    elif problem == "funding":
        payload["funding_account_code"] = "1000"
    elif problem == "owner":
        ApiRequestRecord.objects.filter(domain_object_type="SyncEventRecord").update(client_id="someone_else")
    elif problem == "reversed":
        reverse_journal_entry(entry=JournalEntry.objects.get(pk=old["journal_entry"]["id"]), reversal_date=date(2026, 5, 3), description="Correction")
    before = JournalEntry.objects.count()
    with pytest.raises(ValidationError):
        submit_payment_event(client_id="api_full", idempotency_key="invalid-link", nonce="invalid-link", payload=payload)
    assert settlement_bill.outstanding_balance() == Decimal("100.00")
    assert not Payment.objects.filter(source_id=settlement_bill.pk).exists()
    assert JournalEntry.objects.count() == before


@pytest.mark.django_db
def test_card_payment_closed_period_rolls_back(api_ingestion_ready, settlement_bill):
    from django.core.exceptions import ValidationError
    from apps.accounting.models import AccountingPeriod
    from apps.accounting.services.periods import change_period_status
    from apps.accounting.services.api_ingestion import submit_payment_event
    Account.objects.create(entity=settlement_bill.entity, account_code="2200", name="Card", type="liability", normal_balance="credit")
    change_period_status(period=AccountingPeriod.objects.get(entity=settlement_bill.entity), status="closed")
    before = JournalEntry.objects.count()
    with pytest.raises(ValidationError):
        submit_payment_event(client_id="api_full", idempotency_key="closed-card", nonce="closed-card", payload={
            "source_type": "bill", "source_reference": "BILL-SETTLE", "payment_date": date(2026, 5, 2),
            "amount": Decimal("100.00"), "funding_account_code": "2200"})
    assert settlement_bill.outstanding_balance() == Decimal("100.00")
    assert JournalEntry.objects.count() == before
    assert not Payment.objects.filter(source_id=settlement_bill.pk).exists()


@pytest.mark.django_db
def test_bill_balance_needs_review_after_linked_payment_reversal(api_client, api_ingestion_ready, settlement_bill):
    from apps.accounting.services.api_ingestion import submit_payment_event
    from apps.accounting.services import reverse_journal_entry
    _, result = submit_payment_event(client_id="api_full", idempotency_key="reversed-payment", nonce="reversed-payment", payload={
        "source_type": "bill", "source_reference": "BILL-SETTLE", "payment_date": date(2026, 5, 2), "amount": Decimal("100.00")})
    reverse_journal_entry(entry=JournalEntry.objects.get(pk=result["journal_entry"]["id"]), reversal_date=date(2026, 5, 3), description="Correction")
    response = api_client.get("/api/v1/bills/", {"external_bill_number": "BILL-SETTLE"}, **_signed_headers(
        client_id="api_full", secret="full-secret", path="/api/v1/bills/", method="GET"))
    assert response.data["results"][0]["payment_status"] == "needs_review"
