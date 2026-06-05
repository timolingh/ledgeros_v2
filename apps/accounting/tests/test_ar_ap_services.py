"""Tests for AR/AP service functions: invoice posting, payment application, credits."""
import pytest
from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError

from apps.accounting.models import (
    Account,
    AccountingPeriod,
    Bill,
    BillLine,
    CreditMemo,
    Customer,
    Entity,
    Invoice,
    InvoiceLine,
    JournalEntry,
    Payment,
)
from apps.accounting.services import (
    apply_payment_to_bill,
    apply_payment_to_invoice,
    create_accounting_period,
    issue_customer_credit,
    issue_vendor_credit,
    post_bill,
    post_invoice,
)
from apps.accounting.selectors.balances import account_balance


@pytest.fixture
def entity():
    """Create default entity for tests."""
    return Entity.get_default()


@pytest.fixture
def period(entity):
    """Create an open accounting period."""
    return create_accounting_period(
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
        name="FY2026",
    )


@pytest.fixture
def ar_account(entity):
    """Create an AR control account."""
    return Account.objects.create(
        entity=entity,
        account_code="1200",
        name="Accounts Receivable",
        type=Account.AccountType.ASSET,
        normal_balance=Account.NormalBalance.DEBIT,
    )


@pytest.fixture
def ap_account(entity):
    """Create an AP control account."""
    return Account.objects.create(
        entity=entity,
        account_code="2100",
        name="Accounts Payable",
        type=Account.AccountType.LIABILITY,
        normal_balance=Account.NormalBalance.CREDIT,
    )


@pytest.fixture
def revenue_account(entity):
    """Create a revenue account."""
    return Account.objects.create(
        entity=entity,
        account_code="4000",
        name="Sales Revenue",
        type=Account.AccountType.REVENUE,
        normal_balance=Account.NormalBalance.CREDIT,
    )


@pytest.fixture
def expense_account(entity):
    """Create an expense account."""
    return Account.objects.create(
        entity=entity,
        account_code="5000",
        name="Cost of Goods Sold",
        type=Account.AccountType.EXPENSE,
        normal_balance=Account.NormalBalance.DEBIT,
    )


@pytest.fixture
def cash_account(entity):
    """Create a cash account."""
    return Account.objects.create(
        entity=entity,
        account_code="1000",
        name="Cash",
        type=Account.AccountType.ASSET,
        normal_balance=Account.NormalBalance.DEBIT,
    )


@pytest.fixture
def customer(entity, ar_account):
    """Create a test customer."""
    return Customer.objects.create(
        entity=entity,
        name="ACME Corp",
        customer_code="ACME-001",
        default_ar_account=ar_account,
    )


@pytest.fixture
def vendor(entity, ap_account):
    """Create a test vendor."""
    from apps.accounting.models import Vendor

    return Vendor.objects.create(
        entity=entity,
        name="Widget Supplier",
        vendor_code="WS-001",
        default_ap_account=ap_account,
    )


@pytest.mark.django_db
class TestInvoicePosting:
    """Tests for invoice posting service."""

    def test_post_invoice_creates_journal_entry(self, customer, revenue_account, period):
        """Posting an invoice creates a balanced journal entry."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            line_description="Widget sale",
            amount=Decimal("1000.00"),
        )

        entry = post_invoice(invoice=invoice)

        assert entry.status == JournalEntry.Status.POSTED
        assert entry.total_debits == Decimal("1000.00")
        assert entry.total_credits == Decimal("1000.00")
        assert invoice.status == Invoice.Status.POSTED

    def test_post_invoice_debits_ar_credits_revenue(self, customer, revenue_account, period):
        """Invoice posting creates correct GL lines: Debit AR, Credit Revenue."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-002",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            line_description="Service",
            amount=Decimal("500.00"),
        )

        entry = post_invoice(invoice=invoice)

        # Check AR was debited
        ar_lines = entry.lines.filter(account=customer.default_ar_account)
        assert ar_lines.count() == 1
        assert ar_lines.first().side == "debit"
        assert ar_lines.first().amount == Decimal("500.00")

        # Check Revenue was credited
        revenue_lines = entry.lines.filter(account=revenue_account)
        assert revenue_lines.count() == 1
        assert revenue_lines.first().side == "credit"
        assert revenue_lines.first().amount == Decimal("500.00")

    def test_post_invoice_updates_ar_balance(self, customer, revenue_account, period):
        """Posting invoice increases AR account balance."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-003",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("1000.00"),
        )

        post_invoice(invoice=invoice)

        # AR balance should be 1000 (debit)
        ar_balance = account_balance(customer.default_ar_account)
        assert ar_balance == Decimal("1000.00")

    def test_post_invoice_rejects_non_draft(self, customer, revenue_account, period):
        """Cannot post a non-draft invoice."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-004",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
            status=Invoice.Status.POSTED,
        )
        with pytest.raises(ValidationError):
            post_invoice(invoice=invoice)

    def test_post_invoice_rejects_no_lines(self, customer, period):
        """Cannot post an invoice with no lines."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-005",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            post_invoice(invoice=invoice)

    def test_post_invoice_rejects_no_ar_account(self, entity, revenue_account, period):
        """Cannot post invoice for customer with no AR account."""
        customer_no_ar = Customer.objects.create(
            entity=entity,
            name="No AR",
            customer_code="NOAR",
        )
        invoice = Invoice.objects.create(
            entity=entity,
            customer=customer_no_ar,
            invoice_number="INV-006",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            post_invoice(invoice=invoice)


@pytest.mark.django_db
class TestBillPosting:
    """Tests for bill posting service."""

    def test_post_bill_creates_journal_entry(self, vendor, expense_account, period):
        """Posting a bill creates a balanced journal entry."""
        from apps.accounting.models import Bill

        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        BillLine.objects.create(
            bill=bill,
            account=expense_account,
            line_description="Widget cost",
            amount=Decimal("500.00"),
        )

        entry = post_bill(bill=bill)

        assert entry.status == JournalEntry.Status.POSTED
        assert entry.total_debits == Decimal("500.00")
        assert entry.total_credits == Decimal("500.00")
        assert bill.status == Bill.Status.POSTED

    def test_post_bill_debits_expense_credits_ap(self, vendor, expense_account, period):
        """Bill posting creates correct GL lines: Debit Expense, Credit AP."""
        from apps.accounting.models import Bill

        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-002",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("300.00"),
        )
        BillLine.objects.create(
            bill=bill,
            account=expense_account,
            line_description="Supplies",
            amount=Decimal("300.00"),
        )

        entry = post_bill(bill=bill)

        # Check Expense was debited
        expense_lines = entry.lines.filter(account=expense_account)
        assert expense_lines.count() == 1
        assert expense_lines.first().side == "debit"
        assert expense_lines.first().amount == Decimal("300.00")

        # Check AP was credited
        ap_lines = entry.lines.filter(account=vendor.default_ap_account)
        assert ap_lines.count() == 1
        assert ap_lines.first().side == "credit"
        assert ap_lines.first().amount == Decimal("300.00")

    def test_post_bill_updates_ap_balance(self, vendor, expense_account, period):
        """Posting bill increases AP account balance (credit)."""
        from apps.accounting.models import Bill

        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-003",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        BillLine.objects.create(
            bill=bill,
            account=expense_account,
            amount=Decimal("500.00"),
        )

        post_bill(bill=bill)

        # AP balance should be 500 (credit-normal account, credit of 500)
        ap_balance = account_balance(vendor.default_ap_account)
        assert ap_balance == Decimal("500.00")


@pytest.mark.django_db
class TestPaymentApplication:
    """Tests for payment application services."""

    def test_apply_payment_to_invoice(self, customer, revenue_account, cash_account, period):
        """Applying payment to invoice creates GL entry and updates balance."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("1000.00"),
        )
        post_invoice(invoice=invoice)

        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("400.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )

        app, entry = apply_payment_to_invoice(
            payment=payment,
            invoice=invoice,
            applied_amount=Decimal("400.00"),
        )

        # Check payment application created
        assert app.applied_amount == Decimal("400.00")

        # Check journal entry created and balanced
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.total_debits == Decimal("400.00")
        assert entry.total_credits == Decimal("400.00")

        # Check invoice updated to partially paid
        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PARTIALLY_PAID
        assert invoice.outstanding_balance() == Decimal("600.00")

    def test_apply_payment_to_invoice_full_payment(self, customer, revenue_account, cash_account, period):
        """Applying full payment to invoice sets status to PAID."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-002",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("500.00"),
        )
        post_invoice(invoice=invoice)

        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )

        apply_payment_to_invoice(
            payment=payment,
            invoice=invoice,
            applied_amount=Decimal("500.00"),
        )

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID
        assert invoice.outstanding_balance() == Decimal("0.00")

    def test_apply_payment_to_bill(self, vendor, expense_account, cash_account, period):
        """Applying payment to bill creates GL entry and updates balance."""
        from apps.accounting.models import Bill

        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("300.00"),
        )
        BillLine.objects.create(
            bill=bill,
            account=expense_account,
            amount=Decimal("300.00"),
        )
        post_bill(bill=bill)

        payment = Payment.objects.create(
            entity=vendor.entity,
            source_type=Payment.SourceType.BILL,
            source_id=bill.id,
            amount=Decimal("200.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )

        app, entry = apply_payment_to_bill(
            payment=payment,
            bill=bill,
            applied_amount=Decimal("200.00"),
        )

        # Check payment application created
        assert app.applied_amount == Decimal("200.00")

        # Check journal entry created and balanced
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.total_debits == Decimal("200.00")
        assert entry.total_credits == Decimal("200.00")

        # Check bill updated to partially paid
        bill.refresh_from_db()
        assert bill.status == Bill.Status.PARTIALLY_PAID
        assert bill.outstanding_balance() == Decimal("100.00")

    def test_apply_payment_rejects_wrong_source_type(self, customer, cash_account, period):
        """Cannot apply payment with wrong source type."""
        from apps.accounting.models import Bill

        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.BILL,
            source_id=1,
            amount=Decimal("100.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            apply_payment_to_invoice(
                payment=payment,
                invoice=invoice,
                applied_amount=Decimal("100.00"),
            )


@pytest.mark.django_db
class TestCreditMemos:
    """Tests for credit memo services."""

    def test_issue_customer_credit(self, customer, revenue_account, period):
        """Issuing customer credit creates GL entry and updates balance."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("1000.00"),
        )
        post_invoice(invoice=invoice)

        credit, entry = issue_customer_credit(
            invoice=invoice,
            amount=Decimal("100.00"),
            reason="Return authorization",
        )

        # Check credit memo created
        assert credit.type == CreditMemo.Type.CUSTOMER
        assert credit.amount == Decimal("100.00")

        # Check journal entry created and balanced
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.total_debits == Decimal("100.00")
        assert entry.total_credits == Decimal("100.00")

        # Check invoice updated
        invoice.refresh_from_db()
        assert invoice.outstanding_balance() == Decimal("900.00")

    def test_issue_vendor_credit(self, vendor, expense_account, period):
        """Issuing vendor credit creates GL entry and updates balance."""
        from apps.accounting.models import Bill

        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        BillLine.objects.create(
            bill=bill,
            account=expense_account,
            amount=Decimal("500.00"),
        )
        post_bill(bill=bill)

        credit, entry = issue_vendor_credit(
            bill=bill,
            amount=Decimal("75.00"),
            reason="Overcharge correction",
        )

        # Check credit memo created
        assert credit.type == CreditMemo.Type.VENDOR
        assert credit.amount == Decimal("75.00")

        # Check journal entry created and balanced
        assert entry.status == JournalEntry.Status.POSTED
        assert entry.total_debits == Decimal("75.00")
        assert entry.total_credits == Decimal("75.00")

        # Check bill updated
        bill.refresh_from_db()
        assert bill.outstanding_balance() == Decimal("425.00")

    def test_customer_credit_fully_pays_invoice(self, customer, revenue_account, period):
        """Full customer credit updates invoice status to PAID."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("100.00"),
        )
        post_invoice(invoice=invoice)

        issue_customer_credit(invoice=invoice, amount=Decimal("100.00"))

        invoice.refresh_from_db()
        assert invoice.status == Invoice.Status.PAID
        assert invoice.outstanding_balance() == Decimal("0.00")


@pytest.mark.django_db
class TestARAPBalances:
    """Integration tests for AR/AP balance reconciliation."""

    def test_ar_balance_with_invoice_and_payment(self, customer, revenue_account, cash_account, period):
        """AR balance correctly reflects invoice posting and payment application."""
        ar_account = customer.default_ar_account

        # Initially, AR is zero
        assert account_balance(ar_account) == Decimal("0.00")

        # Post invoice for 1000
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("1000.00"),
        )
        post_invoice(invoice=invoice)

        # AR should be 1000
        assert account_balance(ar_account) == Decimal("1000.00")

        # Apply payment of 600
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("600.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        apply_payment_to_invoice(
            payment=payment,
            invoice=invoice,
            applied_amount=Decimal("600.00"),
        )

        # AR should be 400
        assert account_balance(ar_account) == Decimal("400.00")

        # Issue 100 credit
        issue_customer_credit(invoice=invoice, amount=Decimal("100.00"))

        # AR should be 300
        assert account_balance(ar_account) == Decimal("300.00")
