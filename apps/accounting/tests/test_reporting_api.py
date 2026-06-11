from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.accounting.models import Account, AccountingPeriod, Bill, BillLine, Customer, Invoice, InvoiceLine, Payment, Vendor
from apps.accounting.services import apply_payment_to_bill, apply_payment_to_invoice, create_accounting_period, post_bill, post_invoice
from apps.accounting.services.chart_import import import_chart_of_accounts
from apps.accounting.services.entities import get_default_entity


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="report-tester", password="password")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def reporting_ready(tmp_path):
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
  - code: "2000"
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
    return entity


@pytest.fixture
def reporting_activity(reporting_ready):
    entity = reporting_ready
    ar = Account.objects.get(account_code="1100")
    ap = Account.objects.get(account_code="2000")
    revenue = Account.objects.get(account_code="4000")
    expense = Account.objects.get(account_code="5000")

    customer = Customer.objects.create(entity=entity, name="Widget Corp", customer_code="WID-001", default_ar_account=ar)
    vendor = Vendor.objects.create(entity=entity, name="Tools LLC", vendor_code="VND-001", default_ap_account=ap)

    invoice = Invoice.objects.create(
        entity=entity,
        customer=customer,
        invoice_number="INV-001",
        date=date(2026, 5, 1),
        due_date=date(2026, 6, 1),
        total_amount=Decimal("100.00"),
    )
    InvoiceLine.objects.create(invoice=invoice, account=revenue, line_description="Consulting part 1", amount=Decimal("60.00"))
    InvoiceLine.objects.create(invoice=invoice, account=revenue, line_description="Consulting part 2", amount=Decimal("40.00"))
    post_invoice(invoice=invoice)

    invoice_payment = Payment.objects.create(
        entity=entity,
        source_type=Payment.SourceType.INVOICE,
        source_id=invoice.id,
        amount=Decimal("60.00"),
        payment_date=date(2026, 5, 15),
        account=Account.objects.get(account_code="1000"),
    )
    apply_payment_to_invoice(payment=invoice_payment, invoice=invoice, applied_amount=Decimal("60.00"))

    bill = Bill.objects.create(
        entity=entity,
        vendor=vendor,
        bill_number="BILL-001",
        date=date(2026, 5, 3),
        due_date=date(2026, 6, 3),
        total_amount=Decimal("40.00"),
    )
    BillLine.objects.create(bill=bill, account=expense, line_description="Software license", amount=Decimal("40.00"))
    post_bill(bill=bill)

    bill_payment = Payment.objects.create(
        entity=entity,
        source_type=Payment.SourceType.BILL,
        source_id=bill.id,
        amount=Decimal("40.00"),
        payment_date=date(2026, 5, 16),
        account=Account.objects.get(account_code="1000"),
    )
    apply_payment_to_bill(payment=bill_payment, bill=bill, applied_amount=Decimal("40.00"))

    return {"entity": entity, "invoice": invoice, "bill": bill}


@pytest.mark.django_db
def test_standard_report_endpoints(api_client, reporting_activity):
    balance_sheet = api_client.get("/api/v1/reports/balance_sheet/?as_of=2026-05-31")
    profit_and_loss = api_client.get("/api/v1/reports/profit_and_loss/?start_date=2026-05-01&end_date=2026-05-31&basis=cash")

    assert balance_sheet.status_code == 200
    assert balance_sheet.data["totals"]["difference"] == "0.00"
    assert balance_sheet.data["period"]["status"] == "open"

    assert profit_and_loss.status_code == 200
    assert profit_and_loss.data["basis"] == "cash"
    assert profit_and_loss.data["totals"]["revenue"] == "60.00"
    assert profit_and_loss.data["period"]["status"] == "open"


@pytest.mark.django_db
def test_saved_report_view_can_be_retrieved_rerun_and_drilled_down(api_client, reporting_activity):
    create_response = api_client.post(
        "/api/v1/reports/",
        {
            "name": "May Cash P&L",
            "report_type": "profit_and_loss",
            "basis": "cash",
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "filters": {"department": "ops"},
            "display_settings": {"group_by": "account"},
        },
        format="json",
    )
    assert create_response.status_code == 201
    report_id = create_response.data["id"]

    detail_response = api_client.get(f"/api/v1/reports/{report_id}/")
    run_response = api_client.post(f"/api/v1/reports/{report_id}/run/", {}, format="json")
    drilldown_response = api_client.get(f"/api/v1/reports/{report_id}/drilldown/?account_code=4000")

    assert detail_response.status_code == 200
    assert detail_response.data["name"] == "May Cash P&L"
    assert detail_response.data["filters"] == {"department": "ops"}
    assert detail_response.data["display_settings"] == {"group_by": "account"}

    assert run_response.status_code == 200
    assert run_response.data["basis"] == "cash"
    assert run_response.data["totals"]["revenue"] == "60.00"

    assert drilldown_response.status_code == 200
    assert drilldown_response.data["account_code"] == "4000"
    assert drilldown_response.data["total_amount"] == "60.00"
    assert len(drilldown_response.data["rows"]) == 2
    assert {row["kind"] for row in drilldown_response.data["rows"]} == {"payment_application"}


@pytest.mark.django_db
def test_period_and_tax_report_endpoints(api_client, reporting_ready):
    period = AccountingPeriod.objects.get(name="FY2026")
    period_response = api_client.get(f"/api/v1/periods/{period.pk}/summary/")

    assert period_response.status_code == 200
    assert period_response.data["status"] == "open"

    tax_response = api_client.get("/api/v1/reports/tax_summary/")

    assert tax_response.status_code == 200
    assert tax_response.data["tax_codes"] == []
