from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounting.models import ApiRequestRecord, Account, Bill, Customer, Entity, Invoice, Payment, SyncEventRecord, Vendor
from apps.accounting.services import create_accounting_period
from apps.accounting.services.chart_import import import_chart_of_accounts
from apps.accounting.services.entities import get_default_entity


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


def _signed_headers(*, client_id: str, secret: str, path: str, payload: dict, idempotency_key: str, nonce: str | None = None) -> dict[str, str]:
    nonce = nonce or f"nonce-{idempotency_key}"
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    body_hash = hashlib.sha256(body).hexdigest()
    timestamp = str(int(time.time()))
    message = "\n".join([client_id, "POST", path, timestamp, nonce, body_hash]).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return {
        "HTTP_X_LEDGEROS_CLIENT_ID": client_id,
        "HTTP_X_LEDGEROS_TIMESTAMP": timestamp,
        "HTTP_X_LEDGEROS_NONCE": nonce,
        "HTTP_X_LEDGEROS_SIGNATURE": signature,
        "HTTP_IDEMPOTENCY_KEY": idempotency_key,
    }


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
