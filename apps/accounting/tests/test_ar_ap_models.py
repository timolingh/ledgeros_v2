"""Tests for AR/AP models: Customer, Vendor, Invoice, Bill, Payment, and related records."""
import pytest
from decimal import Decimal
from datetime import date

from django.core.exceptions import ValidationError

from apps.accounting.models import (
    Account,
    Bill,
    BillLine,
    CreditMemo,
    Customer,
    Entity,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentApplication,
    Vendor,
)
from apps.accounting.services import get_or_create_undeposited_funds_account


@pytest.fixture
def entity():
    """Create default entity for tests."""
    return Entity.get_default()


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
def undeposited_funds_account(entity):
    return get_or_create_undeposited_funds_account(entity=entity)


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
    return Vendor.objects.create(
        entity=entity,
        name="Widget Supplier",
        vendor_code="WS-001",
        default_ap_account=ap_account,
    )


@pytest.mark.django_db
class TestCustomer:
    """Tests for Customer model."""

    def test_create_customer(self, entity, ar_account):
        """Customer can be created with required fields."""
        customer = Customer.objects.create(
            entity=entity,
            name="Test Customer",
            customer_code="TEST-001",
            default_ar_account=ar_account,
        )
        assert customer.name == "Test Customer"
        assert customer.customer_code == "TEST-001"
        assert customer.status == Customer.Status.ACTIVE
        assert customer.default_ar_account == ar_account

    def test_customer_code_unique_per_entity(self, entity, ar_account):
        """Customer code must be unique per entity."""
        Customer.objects.create(
            entity=entity,
            name="First",
            customer_code="DUP",
            default_ar_account=ar_account,
        )
        with pytest.raises(Exception):  # IntegrityError
            Customer.objects.create(
                entity=entity,
                name="Second",
                customer_code="DUP",
                default_ar_account=ar_account,
            )

    def test_customer_clean_validates_ar_account_entity(self, entity, ar_account):
        """Customer clean() validates AR account belongs to same entity."""
        other_entity = Entity.objects.create(name="Other", slug="other")
        other_ar = Account.objects.create(
            entity=other_entity,
            account_code="1200",
            name="AR",
            type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT,
        )
        customer = Customer(
            entity=entity,
            name="Test",
            customer_code="TEST",
            default_ar_account=other_ar,
        )
        with pytest.raises(ValidationError):
            customer.clean()

    def test_customer_clean_rejects_inactive_ar_account(self, entity, ar_account):
        """Customer clean() rejects inactive AR account."""
        ar_account.is_active = False
        ar_account.save()
        customer = Customer(
            entity=entity,
            name="Test",
            customer_code="TEST",
            default_ar_account=ar_account,
        )
        with pytest.raises(ValidationError):
            customer.clean()

    def test_customer_inactive_status(self, entity, ar_account):
        """Customer status can be set to inactive."""
        customer = Customer.objects.create(
            entity=entity,
            name="Inactive",
            customer_code="INAC",
            status=Customer.Status.INACTIVE,
            default_ar_account=ar_account,
        )
        assert customer.status == Customer.Status.INACTIVE


@pytest.mark.django_db
class TestVendor:
    """Tests for Vendor model."""

    def test_create_vendor(self, entity, ap_account):
        """Vendor can be created with required fields."""
        vendor = Vendor.objects.create(
            entity=entity,
            name="Test Vendor",
            vendor_code="VEND-001",
            default_ap_account=ap_account,
        )
        assert vendor.name == "Test Vendor"
        assert vendor.vendor_code == "VEND-001"
        assert vendor.status == Vendor.Status.ACTIVE
        assert vendor.default_ap_account == ap_account

    def test_vendor_code_unique_per_entity(self, entity, ap_account):
        """Vendor code must be unique per entity."""
        Vendor.objects.create(
            entity=entity,
            name="First",
            vendor_code="DUP",
            default_ap_account=ap_account,
        )
        with pytest.raises(Exception):  # IntegrityError
            Vendor.objects.create(
                entity=entity,
                name="Second",
                vendor_code="DUP",
                default_ap_account=ap_account,
            )

    def test_vendor_clean_validates_ap_account_entity(self, entity, ap_account):
        """Vendor clean() validates AP account belongs to same entity."""
        other_entity = Entity.objects.create(name="Other", slug="other")
        other_ap = Account.objects.create(
            entity=other_entity,
            account_code="2100",
            name="AP",
            type=Account.AccountType.LIABILITY,
            normal_balance=Account.NormalBalance.CREDIT,
        )
        vendor = Vendor(
            entity=entity,
            name="Test",
            vendor_code="TEST",
            default_ap_account=other_ap,
        )
        with pytest.raises(ValidationError):
            vendor.clean()

    def test_vendor_clean_rejects_inactive_ap_account(self, entity, ap_account):
        """Vendor clean() rejects inactive AP account."""
        ap_account.is_active = False
        ap_account.save()
        vendor = Vendor(
            entity=entity,
            name="Test",
            vendor_code="TEST",
            default_ap_account=ap_account,
        )
        with pytest.raises(ValidationError):
            vendor.clean()


@pytest.mark.django_db
class TestInvoice:
    """Tests for Invoice model."""

    def test_create_invoice(self, customer, revenue_account):
        """Invoice can be created with required fields."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        assert invoice.invoice_number == "INV-001"
        assert invoice.status == Invoice.Status.DRAFT
        assert invoice.outstanding_balance() == Decimal("1000.00")

    def test_invoice_number_unique_per_entity(self, customer):
        """Invoice number must be unique per entity."""
        Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="DUP",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(Exception):  # IntegrityError
            Invoice.objects.create(
                entity=customer.entity,
                customer=customer,
                invoice_number="DUP",
                date=date(2026, 5, 1),
                due_date=date(2026, 6, 1),
                total_amount=Decimal("100.00"),
            )

    def test_invoice_external_invoice_number_unique_per_entity(self, customer):
        """External invoice number must be unique per entity."""
        Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            external_invoice_number="EXT-123",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(Exception):  # IntegrityError
            Invoice.objects.create(
                entity=customer.entity,
                customer=customer,
                invoice_number="INV-002",
                external_invoice_number="EXT-123",
                date=date(2026, 5, 1),
                due_date=date(2026, 6, 1),
                total_amount=Decimal("100.00"),
            )

    def test_invoice_clean_validates_customer_entity(self, entity, customer):
        """Invoice clean() validates customer belongs to same entity."""
        other_entity = Entity.objects.create(name="Other", slug="other")
        invoice = Invoice(
            entity=other_entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            invoice.clean()

    def test_invoice_assert_mutable_draft(self, customer):
        """Draft invoice is mutable."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
            status=Invoice.Status.DRAFT,
        )
        invoice.assert_mutable()  # Should not raise

    def test_invoice_assert_mutable_posted(self, customer):
        """Posted invoice is immutable."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
            status=Invoice.Status.POSTED,
        )
        with pytest.raises(ValidationError):
            invoice.assert_mutable()

    def test_invoice_outstanding_balance_no_payments(self, customer):
        """Outstanding balance equals total_amount when no payments applied."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        assert invoice.outstanding_balance() == Decimal("1000.00")

    def test_invoice_outstanding_balance_with_partial_payment(self, customer, cash_account):
        """Outstanding balance reflects applied payments."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("400.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        PaymentApplication.objects.create(
            payment=payment,
            invoice=invoice,
            applied_amount=Decimal("400.00"),
        )
        assert invoice.outstanding_balance() == Decimal("600.00")


@pytest.mark.django_db
class TestInvoiceLine:
    """Tests for InvoiceLine model."""

    def test_create_invoice_line(self, customer, revenue_account):
        """Invoice line can be created with required fields."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        line = InvoiceLine.objects.create(
            invoice=invoice,
            account=revenue_account,
            line_description="Widget sale",
            amount=Decimal("1000.00"),
        )
        assert line.line_description == "Widget sale"
        assert line.amount == Decimal("1000.00")

    def test_invoice_line_positive_amount_enforced(self, customer, revenue_account):
        """Invoice line amount must be positive."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(Exception):  # IntegrityError
            InvoiceLine.objects.create(
                invoice=invoice,
                account=revenue_account,
                amount=Decimal("-100.00"),
            )

    def test_invoice_line_clean_validates_account_entity(self, customer, revenue_account):
        """Invoice line clean() validates account belongs to same entity."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        other_entity = Entity.objects.create(name="Other", slug="other")
        other_account = Account.objects.create(
            entity=other_entity,
            account_code="4000",
            name="Revenue",
            type=Account.AccountType.REVENUE,
            normal_balance=Account.NormalBalance.CREDIT,
        )
        line = InvoiceLine(
            invoice=invoice,
            account=other_account,
            amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            line.clean()

    def test_invoice_line_clean_rejects_inactive_account(self, customer, revenue_account):
        """Invoice line clean() rejects inactive account."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        revenue_account.is_active = False
        revenue_account.save()
        line = InvoiceLine(
            invoice=invoice,
            account=revenue_account,
            amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            line.clean()


@pytest.mark.django_db
class TestBill:
    """Tests for Bill model."""

    def test_create_bill(self, vendor, expense_account):
        """Bill can be created with required fields."""
        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        assert bill.bill_number == "BILL-001"
        assert bill.status == Bill.Status.DRAFT
        assert bill.outstanding_balance() == Decimal("500.00")

    def test_bill_number_unique_per_entity(self, vendor):
        """Bill number must be unique per entity."""
        Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="DUP",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
        )
        with pytest.raises(Exception):  # IntegrityError
            Bill.objects.create(
                entity=vendor.entity,
                vendor=vendor,
                bill_number="DUP",
                date=date(2026, 5, 1),
                due_date=date(2026, 6, 1),
                total_amount=Decimal("100.00"),
            )

    def test_bill_assert_mutable_draft(self, vendor):
        """Draft bill is mutable."""
        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
            status=Bill.Status.DRAFT,
        )
        bill.assert_mutable()  # Should not raise

    def test_bill_assert_mutable_posted(self, vendor):
        """Posted bill is immutable."""
        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("100.00"),
            status=Bill.Status.POSTED,
        )
        with pytest.raises(ValidationError):
            bill.assert_mutable()

    def test_bill_outstanding_balance_no_payments(self, vendor):
        """Outstanding balance equals total_amount when no payments applied."""
        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        assert bill.outstanding_balance() == Decimal("500.00")


@pytest.mark.django_db
class TestPayment:
    """Tests for Payment model."""

    def test_create_invoice_payment(self, customer, cash_account, undeposited_funds_account):
        """Payment for invoice can be created."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        assert payment.source_type == Payment.SourceType.INVOICE
        assert payment.amount == Decimal("500.00")
        assert payment.account == undeposited_funds_account

    def test_create_bill_payment(self, vendor, cash_account, undeposited_funds_account):
        """Payment for bill can be created."""
        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        payment = Payment.objects.create(
            entity=vendor.entity,
            source_type=Payment.SourceType.BILL,
            source_id=bill.id,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        assert payment.source_type == Payment.SourceType.BILL
        assert payment.account == undeposited_funds_account

    def test_payment_clean_validates_account_entity(self, customer, cash_account):
        """Payment clean() validates account belongs to same entity."""
        other_entity = Entity.objects.create(name="Other", slug="other")
        other_cash = Account.objects.create(
            entity=other_entity,
            account_code="1000",
            name="Cash",
            type=Account.AccountType.ASSET,
            normal_balance=Account.NormalBalance.DEBIT,
        )
        payment = Payment(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=1,
            amount=Decimal("100.00"),
            payment_date=date(2026, 5, 15),
            account=other_cash,
        )
        with pytest.raises(ValidationError):
            payment.clean()

    def test_payment_clean_rejects_inactive_account(self, customer, cash_account):
        """Payment clean() rejects inactive account."""
        cash_account.is_active = False
        cash_account.save()
        payment = Payment(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=1,
            amount=Decimal("100.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        with pytest.raises(ValidationError):
            payment.clean()


@pytest.mark.django_db
class TestPaymentApplication:
    """Tests for PaymentApplication model."""

    def test_create_payment_application(self, customer, cash_account):
        """Payment application can be created."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        app = PaymentApplication.objects.create(
            payment=payment,
            invoice=invoice,
            applied_amount=Decimal("500.00"),
        )
        assert app.applied_amount == Decimal("500.00")

    def test_payment_application_clean_requires_invoice_or_bill(self, customer, cash_account):
        """PaymentApplication clean() requires invoice or bill."""
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=1,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        app = PaymentApplication(
            payment=payment,
            applied_amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            app.clean()

    def test_payment_application_clean_rejects_both_invoice_and_bill(
        self, customer, vendor, cash_account
    ):
        """PaymentApplication clean() rejects both invoice and bill."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        bill = Bill.objects.create(
            entity=vendor.entity,
            vendor=vendor,
            bill_number="BILL-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("500.00"),
        )
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=1,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        app = PaymentApplication(
            payment=payment,
            invoice=invoice,
            bill=bill,
            applied_amount=Decimal("100.00"),
        )
        with pytest.raises(ValidationError):
            app.clean()

    def test_payment_application_clean_rejects_amount_exceeding_payment(
        self, customer, cash_account
    ):
        """PaymentApplication clean() rejects applied amount exceeding payment."""
        invoice = Invoice.objects.create(
            entity=customer.entity,
            customer=customer,
            invoice_number="INV-001",
            date=date(2026, 5, 1),
            due_date=date(2026, 6, 1),
            total_amount=Decimal("1000.00"),
        )
        payment = Payment.objects.create(
            entity=customer.entity,
            source_type=Payment.SourceType.INVOICE,
            source_id=invoice.id,
            amount=Decimal("500.00"),
            payment_date=date(2026, 5, 15),
            account=cash_account,
        )
        app = PaymentApplication(
            payment=payment,
            invoice=invoice,
            applied_amount=Decimal("600.00"),
        )
        with pytest.raises(ValidationError):
            app.clean()


@pytest.mark.django_db
class TestCreditMemo:
    """Tests for CreditMemo model."""

    def test_create_customer_credit(self, customer):
        """Customer credit memo can be created."""
        credit = CreditMemo.objects.create(
            entity=customer.entity,
            type=CreditMemo.Type.CUSTOMER,
            customer=customer,
            amount=Decimal("100.00"),
            memo_date=date(2026, 5, 15),
            reason="Return authorization",
        )
        assert credit.type == CreditMemo.Type.CUSTOMER
        assert credit.amount == Decimal("100.00")

    def test_create_vendor_credit(self, vendor):
        """Vendor credit memo can be created."""
        credit = CreditMemo.objects.create(
            entity=vendor.entity,
            type=CreditMemo.Type.VENDOR,
            vendor=vendor,
            amount=Decimal("75.00"),
            memo_date=date(2026, 5, 15),
            reason="Overcharge correction",
        )
        assert credit.type == CreditMemo.Type.VENDOR
        assert credit.amount == Decimal("75.00")

    def test_credit_memo_clean_requires_customer_or_vendor(self, customer):
        """CreditMemo clean() requires customer or vendor."""
        credit = CreditMemo(
            entity=customer.entity,
            type=CreditMemo.Type.CUSTOMER,
            amount=Decimal("100.00"),
            memo_date=date(2026, 5, 15),
        )
        with pytest.raises(ValidationError):
            credit.clean()

    def test_credit_memo_clean_rejects_both_customer_and_vendor(self, customer, vendor):
        """CreditMemo clean() rejects both customer and vendor."""
        credit = CreditMemo(
            entity=customer.entity,
            type=CreditMemo.Type.CUSTOMER,
            customer=customer,
            vendor=vendor,
            amount=Decimal("100.00"),
            memo_date=date(2026, 5, 15),
        )
        with pytest.raises(ValidationError):
            credit.clean()
