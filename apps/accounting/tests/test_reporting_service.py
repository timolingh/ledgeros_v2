from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from apps.accounting.models import Account, AccountingPeriod, Bill, BillLine, Customer, Invoice, InvoiceLine, Payment, Vendor
from apps.accounting.services import (
    JournalLineInput,
    apply_payment_to_bill,
    apply_payment_to_invoice,
    change_period_status,
    create_accounting_period,
    create_and_post_journal_entry,
    generate_balance_sheet,
    generate_profit_and_loss,
    generate_report_drilldown,
    get_default_entity,
    post_bill,
    post_invoice,
    run_report_view,
    save_report_view,
    save_tax_code,
    summarize_period,
    tax_summary,
)
from apps.accounting.services.chart_import import import_chart_of_accounts


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
  - code: "3000"
    name: Owner Equity
    type: equity
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

    return {
        "entity": entity,
        "invoice": invoice,
        "bill": bill,
    }


@pytest.mark.django_db
def test_balance_sheet_balances_with_current_earnings(reporting_activity):
    report = generate_balance_sheet(entity=reporting_activity["entity"], as_of=date(2026, 5, 31))

    assert report["report_type"] == "balance_sheet"
    assert report["period"]["status"] == "open"
    assert report["totals"]["assets"] == "60.00"
    assert report["totals"]["liabilities"] == "0.00"
    assert report["totals"]["equity"] == "60.00"
    assert report["totals"]["net_income"] == "60.00"
    assert report["totals"]["difference"] == "0.00"
    equity_rows = report["sections"][2]["accounts"]
    assert any(row.get("synthetic") for row in equity_rows)


@pytest.mark.django_db
def test_profit_and_loss_supports_cash_and_accrual_basis(reporting_activity):
    accrual = generate_profit_and_loss(
        entity=reporting_activity["entity"],
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        basis="accrual",
    )
    cash = generate_profit_and_loss(
        entity=reporting_activity["entity"],
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        basis="cash",
    )

    assert accrual["basis"] == "accrual"
    assert accrual["period"]["status"] == "open"
    assert accrual["totals"] == {"revenue": "100.00", "expense": "40.00", "net_income": "60.00"}
    assert cash["basis"] == "cash"
    assert cash["period"]["status"] == "open"
    assert cash["totals"] == {"revenue": "60.00", "expense": "40.00", "net_income": "20.00"}


@pytest.mark.django_db
def test_revenue_debit_reduces_accrual_p_and_l_revenue(reporting_ready):
    create_accounting_period(start_date=date(2030, 1, 1), end_date=date(2030, 12, 31), name="FY2030")
    create_and_post_journal_entry(
        entry_date=date(2030, 5, 1),
        description="Revenue recognition",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    create_and_post_journal_entry(
        entry_date=date(2030, 5, 20),
        description="Revenue credit memo",
        lines=[
            JournalLineInput(account_code="4000", side="debit", amount="25.00"),
            JournalLineInput(account_code="1000", side="credit", amount="25.00"),
        ],
    )

    report = generate_profit_and_loss(
        entity=reporting_ready,
        start_date=date(2030, 5, 1),
        end_date=date(2030, 5, 31),
        basis="accrual",
    )

    assert report["totals"] == {"revenue": "75.00", "expense": "0.00", "net_income": "75.00"}


@pytest.mark.django_db
def test_period_summary_uses_only_period_activity(reporting_ready):
    create_accounting_period(start_date=date(2032, 1, 1), end_date=date(2032, 1, 31), name="Jan 2032 Period Summary Test")
    may = create_accounting_period(start_date=date(2032, 5, 1), end_date=date(2032, 5, 31), name="May 2032 Period Summary Test")

    create_and_post_journal_entry(
        entry_date=date(2032, 1, 15),
        description="January activity",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="10.00"),
            JournalLineInput(account_code="4000", side="credit", amount="10.00"),
        ],
    )

    create_and_post_journal_entry(
        entry_date=date(2032, 5, 15),
        description="May activity",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="20.00"),
            JournalLineInput(account_code="4000", side="credit", amount="20.00"),
        ],
    )

    summary = summarize_period(period=may)

    assert summary["journal_entry_count"] == 1
    assert summary["posted_debits"] == "20.00"
    assert summary["posted_credits"] == "20.00"
    assert summary["balance_check"] == "0.00"


@pytest.mark.django_db
def test_report_drilldown_exposes_journal_entries_and_payment_applications(reporting_activity):
    accrual_detail = generate_report_drilldown(
        entity=reporting_activity["entity"],
        report_type="profit_and_loss",
        account_code="4000",
        basis="accrual",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )
    cash_detail = generate_report_drilldown(
        entity=reporting_activity["entity"],
        report_type="profit_and_loss",
        account_code="4000",
        basis="cash",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
    )

    assert accrual_detail["total_amount"] == "100.00"
    assert len(accrual_detail["rows"]) == 2
    assert {row["kind"] for row in accrual_detail["rows"]} == {"journal_line"}
    assert cash_detail["total_amount"] == "60.00"
    assert len(cash_detail["rows"]) == 2
    assert {row["kind"] for row in cash_detail["rows"]} == {"payment_application"}
    assert {row["allocated_amount"] for row in cash_detail["rows"]} == {"36.00", "24.00"}


@pytest.mark.django_db
def test_saved_report_view_persists_and_runs(reporting_activity):
    report_view = save_report_view(
        entity=reporting_activity["entity"],
        name="May P&L",
        report_type="profit_and_loss",
        basis="cash",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 31),
        filters={"department": "ops"},
        display_settings={"group_by": "account"},
    )
    report = run_report_view(report_view=report_view)

    assert report_view.name == "May P&L"
    assert report_view.filters == {"department": "ops"}
    assert report_view.display_settings == {"group_by": "account"}
    assert report["basis"] == "cash"
    assert report["totals"]["revenue"] == "60.00"


@pytest.mark.django_db
def test_period_summary_reflects_closed_status(reporting_ready):
    period = AccountingPeriod.objects.get(name="FY2026")
    change_period_status(period=period, status=AccountingPeriod.Status.CLOSED)

    summary = summarize_period(period=period)

    assert summary["status"] == AccountingPeriod.Status.CLOSED
    assert summary["balance_check"] == "0.00"


@pytest.mark.django_db
def test_tax_summary_includes_liability_accounts_and_balances(reporting_ready):
    tax_liability = Account.objects.get(account_code="2000")
    save_tax_code(
        entity=reporting_ready,
        code="CA-STD",
        name="California sales tax",
        rate=Decimal("0.0750"),
        jurisdiction="ca",
        liability_account=tax_liability,
    )
    create_and_post_journal_entry(
        entry_date=date(2026, 5, 20),
        description="Tax accrual",
        lines=[
            JournalLineInput(account_code="5000", side="debit", amount="12.34"),
            JournalLineInput(account_code="2000", side="credit", amount="12.34"),
        ],
    )

    report = tax_summary(entity=reporting_ready)
    tax_code = report["tax_codes"][0]

    assert report["entity_id"] == reporting_ready.id
    assert tax_code["code"] == "CA-STD"
    assert tax_code["jurisdiction"] == "ca"
    assert tax_code["liability_account_code"] == "2000"
    assert tax_code["liability_balance"] == "12.34"
