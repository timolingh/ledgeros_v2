from decimal import Decimal

import pytest

from apps.accounting.models import Bill, JournalEntry
from apps.accounting.tests.test_api_ingestion import api_client, api_ingestion_ready, _signed_headers


def bill_payload(**extra):
    return {"vendor_code": "API-VEND-001", "external_bill_number": "vendor-bill:42",
            "bill_date": "2026-05-04", "due_date": "2026-06-04", "total_amount": "120.00",
            "lines": [{"account_code": "5000", "line_description": "Expense", "amount": "120.00"}], **extra}


def submit(client, ready, payload, nonce="supplier-1"):
    return client.post("/api/v1/bills/", payload, format="json", **_signed_headers(
        client_id="api_full", secret=ready["clients"]["api_full"], path="/api/v1/bills/",
        payload=payload, idempotency_key="supplier-bill", nonce=nonce))


@pytest.mark.django_db
def test_supplier_reference_posts_reads_and_replays_without_new_journal(api_client, api_ingestion_ready):
    payload = bill_payload(supplier_invoice_number="SUP-0042")
    first = submit(api_client, api_ingestion_ready, payload)
    assert first.status_code == 201
    assert first.data["bill"]["supplier_invoice_number"] == "SUP-0042"
    bill = Bill.objects.get(pk=first.data["bill"]["id"])
    assert bill.supplier_invoice_number == "SUP-0042"
    assert bill.external_bill_number == "vendor-bill:42"
    journal = JournalEntry.objects.get(pk=first.data["journal_entry"]["id"])
    assert sorted(journal.lines.values_list("account__account_code", "side", "amount")) == [
        ("2100", "credit", Decimal("120.00")), ("5000", "debit", Decimal("120.00"))]
    replay = submit(api_client, api_ingestion_ready, payload, "supplier-2")
    assert replay.status_code == 201
    assert replay.data == first.data
    assert Bill.objects.count() == 1
    assert JournalEntry.objects.count() == 1
    response = api_client.get("/api/v1/bills/", {"external_bill_number": "vendor-bill:42"}, **_signed_headers(
        client_id="api_full", secret=api_ingestion_ready["clients"]["api_full"],
        path="/api/v1/bills/", method="GET", nonce="supplier-read"))
    assert response.status_code == 200
    assert response.data["results"][0]["supplier_invoice_number"] == "SUP-0042"
    changed = submit(api_client, api_ingestion_ready, bill_payload(supplier_invoice_number="DIFFERENT"), "supplier-3")
    assert changed.status_code == 400
    bill.refresh_from_db()
    assert bill.supplier_invoice_number == "SUP-0042"
    assert JournalEntry.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("extra", [{}, {"supplier_invoice_number": ""}])
def test_supplier_reference_is_optional(api_client, api_ingestion_ready, extra):
    first = submit(api_client, api_ingestion_ready, bill_payload(**extra))
    assert first.status_code == 201
    assert first.data["bill"]["supplier_invoice_number"] == ""
    assert Bill.objects.get().supplier_invoice_number == ""
    assert submit(api_client, api_ingestion_ready, bill_payload(**extra), "optional-retry").data == first.data


@pytest.mark.django_db
def test_supplier_reference_length_rejected_before_posting(api_client, api_ingestion_ready):
    response = submit(api_client, api_ingestion_ready, bill_payload(supplier_invoice_number="x" * 256))
    assert response.status_code == 400
    assert not Bill.objects.exists()
    assert not JournalEntry.objects.exists()
