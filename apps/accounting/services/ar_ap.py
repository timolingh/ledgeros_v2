"""AR/AP service layer for invoice, bill, payment, and credit operations."""
from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import (
    Bill,
    BillLine,
    CreditMemo,
    Invoice,
    InvoiceLine,
    JournalEntry,
    Payment,
    PaymentApplication,
)
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.posting import JournalLineInput, create_and_post_journal_entry
from apps.accounting.services.writes import get_or_create_undeposited_funds_account

if TYPE_CHECKING:
    from django.contrib.auth import get_user_model

    User = get_user_model()


@transaction.atomic
def post_invoice(*, invoice: Invoice, user: User | None = None, source: str = "manual") -> JournalEntry:
    """
    Post an invoice by creating a journal entry.

    Debit: Accounts Receivable (from invoice.customer.default_ar_account or first invoice line)
    Credit: Revenue accounts (from invoice lines)

    Returns the created journal entry.
    """
    if invoice.status != Invoice.Status.DRAFT:
        raise ValidationError("Only draft invoices can be posted.")

    if not invoice.lines.exists():
        raise ValidationError("Invoice must have at least one line to post.")

    # Determine AR account (use customer default or fall back to first line AR account)
    ar_account = invoice.customer.default_ar_account
    if not ar_account:
        raise ValidationError(f"Customer {invoice.customer.customer_code} has no default AR account configured.")

    # Build journal lines: total debit to AR, individual credits to revenue accounts
    total_amount = Decimal("0.00")
    credit_lines = []

    for line in invoice.lines.all():
        if not line.account:
            raise ValidationError(f"Invoice line must have an account specified.")
        credit_lines.append(
            JournalLineInput(
                account_code=line.account.account_code,
                side="credit",
                amount=line.amount,
                description=f"Invoice {invoice.invoice_number}: {line.line_description}",
            )
        )
        total_amount += line.amount

    # Create the journal entry
    entry = create_and_post_journal_entry(
        entry_date=invoice.date,
        description=f"Invoice {invoice.invoice_number} from {invoice.customer.name}",
        lines=[
            JournalLineInput(
                account_code=ar_account.account_code,
                side="debit",
                amount=total_amount,
                description=f"AR for invoice {invoice.invoice_number}",
            ),
            *credit_lines,
        ],
        created_by=user,
        source=source,
    )

    # Update invoice status
    invoice.status = Invoice.Status.POSTED
    invoice.save(update_fields=["status", "updated_at"])

    audit_success(
        action="invoice_posted",
        record=invoice,
        user=user,
        source=source,
        metadata={"journal_entry_id": entry.id, "total_amount": str(total_amount)},
    )

    return entry


@transaction.atomic
def post_bill(*, bill: Bill, user: User | None = None, source: str = "manual") -> JournalEntry:
    """
    Post a bill by creating a journal entry.

    Debit: Expense accounts (from bill lines)
    Credit: Accounts Payable (from bill.vendor.default_ap_account or first bill line)

    Returns the created journal entry.
    """
    if bill.status != Bill.Status.DRAFT:
        raise ValidationError("Only draft bills can be posted.")

    if not bill.lines.exists():
        raise ValidationError("Bill must have at least one line to post.")

    # Determine AP account (use vendor default or fall back to first line AP account)
    ap_account = bill.vendor.default_ap_account
    if not ap_account:
        raise ValidationError(f"Vendor {bill.vendor.vendor_code} has no default AP account configured.")

    # Build journal lines: individual debits to expense accounts, total credit to AP
    total_amount = Decimal("0.00")
    debit_lines = []

    for line in bill.lines.all():
        if not line.account:
            raise ValidationError(f"Bill line must have an account specified.")
        debit_lines.append(
            JournalLineInput(
                account_code=line.account.account_code,
                side="debit",
                amount=line.amount,
                description=f"Bill {bill.bill_number}: {line.line_description}",
            )
        )
        total_amount += line.amount

    # Create the journal entry
    entry = create_and_post_journal_entry(
        entry_date=bill.date,
        description=f"Bill {bill.bill_number} from {bill.vendor.name}",
        lines=[
            *debit_lines,
            JournalLineInput(
                account_code=ap_account.account_code,
                side="credit",
                amount=total_amount,
                description=f"AP for bill {bill.bill_number}",
            ),
        ],
        created_by=user,
        source=source,
    )

    # Update bill status
    bill.status = Bill.Status.POSTED
    bill.save(update_fields=["status", "updated_at"])

    audit_success(
        action="bill_posted",
        record=bill,
        user=user,
        source=source,
        metadata={"journal_entry_id": entry.id, "total_amount": str(total_amount)},
    )

    return entry


@transaction.atomic
def apply_payment_to_invoice(
    *, payment: Payment, invoice: Invoice, applied_amount: Decimal, user: User | None = None, source: str = "manual"
) -> tuple[PaymentApplication, JournalEntry]:
    """
    Apply a payment to an invoice.

    Creates a journal entry: Debit Undeposited Funds, Credit AR
    Updates invoice status based on remaining balance.
    Returns the PaymentApplication and the journal entry.
    """
    if payment.source_type != Payment.SourceType.INVOICE:
        raise ValidationError("Payment must be for an invoice source type.")

    if applied_amount <= Decimal("0.00"):
        raise ValidationError("Applied amount must be positive.")

    if applied_amount > payment.amount:
        raise ValidationError(f"Applied amount cannot exceed payment amount of {payment.amount}.")

    clearing_account = get_or_create_undeposited_funds_account(entity=payment.entity)
    if payment.account_id != clearing_account.id:
        payment.account = clearing_account
        payment.save(update_fields=["account"])

    # Get AR account from customer
    ar_account = invoice.customer.default_ar_account
    if not ar_account:
        raise ValidationError(f"Customer {invoice.customer.customer_code} has no default AR account configured.")

    # Create journal entry: Debit Undeposited Funds, Credit AR
    entry = create_and_post_journal_entry(
        entry_date=payment.payment_date,
        description=f"Payment for invoice {invoice.invoice_number}",
        lines=[
            JournalLineInput(
                account_code=clearing_account.account_code,
                side="debit",
                amount=applied_amount,
                description=f"Undeposited receipt for invoice {invoice.invoice_number}",
            ),
            JournalLineInput(
                account_code=ar_account.account_code,
                side="credit",
                amount=applied_amount,
                description=f"AR reduction for invoice {invoice.invoice_number}",
            ),
        ],
        created_by=user,
        source=source,
    )

    # Create payment application
    app = PaymentApplication.objects.create(
        payment=payment,
        invoice=invoice,
        applied_amount=applied_amount,
    )

    # Update invoice status based on remaining balance
    remaining = invoice.outstanding_balance()
    if remaining <= Decimal("0.00"):
        invoice.status = Invoice.Status.PAID
    elif remaining < invoice.total_amount:
        invoice.status = Invoice.Status.PARTIALLY_PAID
    invoice.save(update_fields=["status", "updated_at"])

    audit_success(
        action="payment_applied_to_invoice",
        record=app,
        user=user,
        source=source,
        metadata={
            "invoice_id": invoice.id,
            "applied_amount": str(applied_amount),
            "remaining_balance": str(remaining),
            "journal_entry_id": entry.id,
        },
    )

    return app, entry


@transaction.atomic
def apply_payment_to_bill(
    *, payment: Payment, bill: Bill, applied_amount: Decimal, user: User | None = None, source: str = "manual"
) -> tuple[PaymentApplication, JournalEntry]:
    """
    Apply a payment to a bill.

    Creates a journal entry: Debit AP, Credit Undeposited Funds
    Updates bill status based on remaining balance.
    Returns the PaymentApplication and the journal entry.
    """
    if payment.source_type != Payment.SourceType.BILL:
        raise ValidationError("Payment must be for a bill source type.")

    if applied_amount <= Decimal("0.00"):
        raise ValidationError("Applied amount must be positive.")

    if applied_amount > payment.amount:
        raise ValidationError(f"Applied amount cannot exceed payment amount of {payment.amount}.")

    clearing_account = get_or_create_undeposited_funds_account(entity=payment.entity)
    if payment.account_id != clearing_account.id:
        payment.account = clearing_account
        payment.save(update_fields=["account"])

    # Get AP account from vendor
    ap_account = bill.vendor.default_ap_account
    if not ap_account:
        raise ValidationError(f"Vendor {bill.vendor.vendor_code} has no default AP account configured.")

    # Create journal entry: Debit AP, Credit Undeposited Funds
    entry = create_and_post_journal_entry(
        entry_date=payment.payment_date,
        description=f"Payment for bill {bill.bill_number}",
        lines=[
            JournalLineInput(
                account_code=ap_account.account_code,
                side="debit",
                amount=applied_amount,
                description=f"AP reduction for bill {bill.bill_number}",
            ),
            JournalLineInput(
                account_code=clearing_account.account_code,
                side="credit",
                amount=applied_amount,
                description=f"Undeposited payment for bill {bill.bill_number}",
            ),
        ],
        created_by=user,
        source=source,
    )

    # Create payment application
    app = PaymentApplication.objects.create(
        payment=payment,
        bill=bill,
        applied_amount=applied_amount,
    )

    # Update bill status based on remaining balance
    remaining = bill.outstanding_balance()
    if remaining <= Decimal("0.00"):
        bill.status = Bill.Status.PAID
    elif remaining < bill.total_amount:
        bill.status = Bill.Status.PARTIALLY_PAID
    bill.save(update_fields=["status", "updated_at"])

    audit_success(
        action="payment_applied_to_bill",
        record=app,
        user=user,
        source=source,
        metadata={
            "bill_id": bill.id,
            "applied_amount": str(applied_amount),
            "remaining_balance": str(remaining),
            "journal_entry_id": entry.id,
        },
    )

    return app, entry


@transaction.atomic
def issue_customer_credit(
    *, invoice: Invoice, amount: Decimal, reason: str = "", user: User | None = None, source: str = "manual"
) -> tuple[CreditMemo, JournalEntry]:
    """
    Issue a credit memo to a customer.

    Creates a journal entry: Debit Revenue/Liability, Credit AR
    Creates a payment application to reduce outstanding balance.
    Returns the CreditMemo and the journal entry.
    """
    if amount <= Decimal("0.00"):
        raise ValidationError("Credit amount must be positive.")

    ar_account = invoice.customer.default_ar_account
    if not ar_account:
        raise ValidationError(f"Customer {invoice.customer.customer_code} has no default AR account configured.")

    # Create credit memo
    credit = CreditMemo.objects.create(
        entity=invoice.entity,
        type=CreditMemo.Type.CUSTOMER,
        customer=invoice.customer,
        amount=amount,
        memo_date=timezone.now().date(),
        reason=reason,
    )

    # Create journal entry: Debit Revenue (reduce income), Credit AR (reduce receivable)
    # For simplicity, we debit the first revenue account from the invoice
    revenue_line = invoice.lines.first()
    if not revenue_line:
        raise ValidationError("Invoice must have at least one line to issue credit.")

    entry = create_and_post_journal_entry(
        entry_date=credit.memo_date,
        description=f"Customer credit memo for {invoice.customer.name}",
        lines=[
            JournalLineInput(
                account_code=revenue_line.account.account_code,
                side="debit",
                amount=amount,
                description=f"Credit reversal for invoice {invoice.invoice_number}",
            ),
            JournalLineInput(
                account_code=ar_account.account_code,
                side="credit",
                amount=amount,
                description=f"AR reduction for customer credit",
            ),
        ],
        created_by=user,
        source=source,
    )

    # Create a "payment" record for the credit (source_id points to credit memo)
    # We use a synthetic payment to apply the credit to the invoice
    credit_payment = Payment.objects.create(
        entity=invoice.entity,
        source_type=Payment.SourceType.INVOICE,
        source_id=invoice.id,
        amount=amount,
        payment_date=credit.memo_date,
        account=ar_account,  # Dummy account, not used for GL in this context
        is_credit_adjustment=True,
    )

    # Create payment application to reduce outstanding balance
    PaymentApplication.objects.create(
        payment=credit_payment,
        invoice=invoice,
        applied_amount=amount,
    )

    # Update invoice status if fully credited
    remaining = invoice.outstanding_balance()
    if remaining <= Decimal("0.00"):
        invoice.status = Invoice.Status.PAID
        invoice.save(update_fields=["status", "updated_at"])

    audit_success(
        action="customer_credit_issued",
        record=credit,
        user=user,
        source=source,
        metadata={
            "invoice_id": invoice.id,
            "amount": str(amount),
            "reason": reason,
            "journal_entry_id": entry.id,
        },
    )

    return credit, entry


@transaction.atomic
def issue_vendor_credit(
    *, bill: Bill, amount: Decimal, reason: str = "", user: User | None = None, source: str = "manual"
) -> tuple[CreditMemo, JournalEntry]:
    """
    Issue a credit memo to a vendor.

    Creates a journal entry: Debit AP, Credit Expense/Asset
    Creates a payment application to reduce outstanding balance.
    Returns the CreditMemo and the journal entry.
    """
    if amount <= Decimal("0.00"):
        raise ValidationError("Credit amount must be positive.")

    ap_account = bill.vendor.default_ap_account
    if not ap_account:
        raise ValidationError(f"Vendor {bill.vendor.vendor_code} has no default AP account configured.")

    # Create credit memo
    credit = CreditMemo.objects.create(
        entity=bill.entity,
        type=CreditMemo.Type.VENDOR,
        vendor=bill.vendor,
        amount=amount,
        memo_date=timezone.now().date(),
        reason=reason,
    )

    # Create journal entry: Debit AP (reduce payable), Credit Expense (reduce cost)
    # For simplicity, we credit the first expense account from the bill
    expense_line = bill.lines.first()
    if not expense_line:
        raise ValidationError("Bill must have at least one line to issue credit.")

    entry = create_and_post_journal_entry(
        entry_date=credit.memo_date,
        description=f"Vendor credit memo for {bill.vendor.name}",
        lines=[
            JournalLineInput(
                account_code=ap_account.account_code,
                side="debit",
                amount=amount,
                description=f"AP reduction for vendor credit",
            ),
            JournalLineInput(
                account_code=expense_line.account.account_code,
                side="credit",
                amount=amount,
                description=f"Cost reduction for bill {bill.bill_number}",
            ),
        ],
        created_by=user,
        source=source,
    )

    # Create a "payment" record for the credit (source_id points to credit memo)
    # We use a synthetic payment to apply the credit to the bill
    credit_payment = Payment.objects.create(
        entity=bill.entity,
        source_type=Payment.SourceType.BILL,
        source_id=bill.id,
        amount=amount,
        payment_date=credit.memo_date,
        account=ap_account,  # Dummy account, not used for GL in this context
        is_credit_adjustment=True,
    )

    # Create payment application to reduce outstanding balance
    PaymentApplication.objects.create(
        payment=credit_payment,
        bill=bill,
        applied_amount=amount,
    )

    # Update bill status if fully credited
    remaining = bill.outstanding_balance()
    if remaining <= Decimal("0.00"):
        bill.status = Bill.Status.PAID
        bill.save(update_fields=["status", "updated_at"])

    audit_success(
        action="vendor_credit_issued",
        record=credit,
        user=user,
        source=source,
        metadata={
            "bill_id": bill.id,
            "amount": str(amount),
            "reason": reason,
            "journal_entry_id": entry.id,
        },
    )

    return credit, entry
