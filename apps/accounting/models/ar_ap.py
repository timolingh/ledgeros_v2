from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from .accounts import Account, Entity


class Customer(models.Model):
    """Customer accounting record for AR tracking."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="customers")
    name = models.CharField(max_length=255)
    customer_code = models.CharField(max_length=64)
    default_ar_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="customers_with_default_ar",
        help_text="Default AR account for invoices created for this customer. Can be overridden per invoice line.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "customer_code"], name="unique_customer_code_per_entity"),
        ]
        ordering = ["customer_code"]

    def __str__(self) -> str:
        return f"{self.customer_code} - {self.name}"

    def clean(self) -> None:
        if self.default_ar_account and self.default_ar_account.entity_id != self.entity_id:
            raise ValidationError({"default_ar_account": "AR account must belong to the same entity."})
        if self.default_ar_account and not self.default_ar_account.is_active:
            raise ValidationError({"default_ar_account": "AR account must be active."})


class Vendor(models.Model):
    """Vendor accounting record for AP tracking."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="vendors")
    name = models.CharField(max_length=255)
    vendor_code = models.CharField(max_length=64)
    default_ap_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="vendors_with_default_ap",
        help_text="Default AP account for bills created for this vendor. Can be overridden per bill line.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "vendor_code"], name="unique_vendor_code_per_entity"),
        ]
        ordering = ["vendor_code"]

    def __str__(self) -> str:
        return f"{self.vendor_code} - {self.name}"

    def clean(self) -> None:
        if self.default_ap_account and self.default_ap_account.entity_id != self.entity_id:
            raise ValidationError({"default_ap_account": "AP account must belong to the same entity."})
        if self.default_ap_account and not self.default_ap_account.is_active:
            raise ValidationError({"default_ap_account": "AP account must be active."})


class Invoice(models.Model):
    """Customer invoice accounting record."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"
        VOIDED = "voided", "Voided"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="invoices")
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="invoices")
    invoice_number = models.CharField(max_length=64, help_text="Internal invoice number, unique per entity.")
    external_invoice_number = models.CharField(
        max_length=255,
        blank=True,
        help_text="External invoice number from API source, if applicable.",
    )
    external_source_client_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="External API client identifier that supplied the external invoice number.",
    )
    date = models.DateField()
    due_date = models.DateField()
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total invoice amount, should match sum of line amounts.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "invoice_number"], name="unique_invoice_number_per_entity"),
            models.UniqueConstraint(
                fields=["entity", "external_source_client_id", "external_invoice_number"],
                condition=Q(external_invoice_number__gt=""),
                name="unique_external_invoice_number_per_client_per_entity",
            ),
        ]
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number} ({self.date})"

    def calculated_total(self) -> Decimal:
        """Calculate total from invoice lines."""
        return self.lines.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def outstanding_balance(self) -> Decimal:
        """Outstanding balance = total_amount - sum of applied payments."""
        applied = self.payment_applications.aggregate(total=Sum("applied_amount"))["total"] or Decimal("0.00")
        return self.total_amount - applied

    def clean(self) -> None:
        if self.customer.entity_id != self.entity_id:
            raise ValidationError({"customer": "Customer must belong to the same entity."})

    def assert_mutable(self) -> None:
        if self.status not in {self.Status.DRAFT}:
            raise ValidationError("Only draft invoices may be edited destructively.")


class InvoiceLine(models.Model):
    """Individual line item on a customer invoice."""

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        help_text="Account to credit when this line is posted. Usually revenue account.",
    )
    line_description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(check=Q(amount__gt=0), name="invoice_line_positive_amount")]

    def __str__(self) -> str:
        return f"{self.line_description or 'Line'} {self.amount}"

    def clean(self) -> None:
        if self.invoice_id and self.account_id and self.invoice.entity_id != self.account.entity_id:
            raise ValidationError("Account must belong to the same entity as the invoice.")
        if self.account_id and not self.account.is_active:
            raise ValidationError({"account": "Account must be active."})


class Bill(models.Model):
    """Vendor bill accounting record."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        PARTIALLY_PAID = "partially_paid", "Partially Paid"
        PAID = "paid", "Paid"
        VOIDED = "voided", "Voided"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="bills")
    vendor = models.ForeignKey(Vendor, on_delete=models.PROTECT, related_name="bills")
    bill_number = models.CharField(max_length=64, help_text="Internal bill number, unique per entity.")
    external_bill_number = models.CharField(
        max_length=255,
        blank=True,
        help_text="External bill number from API source, if applicable.",
    )
    external_source_client_id = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="External API client identifier that supplied the external bill number.",
    )
    date = models.DateField()
    due_date = models.DateField()
    total_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Total bill amount, should match sum of line amounts.",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "bill_number"], name="unique_bill_number_per_entity"),
            models.UniqueConstraint(
                fields=["entity", "external_source_client_id", "external_bill_number"],
                condition=Q(external_bill_number__gt=""),
                name="unique_external_bill_number_per_client_per_entity",
            ),
        ]
        ordering = ["-date", "-id"]

    def __str__(self) -> str:
        return f"Bill {self.bill_number} ({self.date})"

    def calculated_total(self) -> Decimal:
        """Calculate total from bill lines."""
        return self.lines.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def outstanding_balance(self) -> Decimal:
        """Outstanding balance = total_amount - sum of applied payments."""
        applied = self.payment_applications.aggregate(total=Sum("applied_amount"))["total"] or Decimal("0.00")
        return self.total_amount - applied

    def clean(self) -> None:
        if self.vendor.entity_id != self.entity_id:
            raise ValidationError({"vendor": "Vendor must belong to the same entity."})

    def assert_mutable(self) -> None:
        if self.status not in {self.Status.DRAFT}:
            raise ValidationError("Only draft bills may be edited destructively.")


class BillLine(models.Model):
    """Individual line item on a vendor bill."""

    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        help_text="Account to debit when this line is posted. Usually expense or asset account.",
    )
    line_description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(check=Q(amount__gt=0), name="bill_line_positive_amount")]

    def __str__(self) -> str:
        return f"{self.line_description or 'Line'} {self.amount}"

    def clean(self) -> None:
        if self.bill_id and self.account_id and self.bill.entity_id != self.account.entity_id:
            raise ValidationError("Account must belong to the same entity as the bill.")
        if self.account_id and not self.account.is_active:
            raise ValidationError({"account": "Account must be active."})


class Payment(models.Model):
    """Payment record for customer payments or vendor payments."""

    class SourceType(models.TextChoices):
        INVOICE = "invoice", "Customer Invoice"
        BILL = "bill", "Vendor Bill"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="payments")
    source_type = models.CharField(
        max_length=16,
        choices=SourceType.choices,
        help_text="Whether this payment is for an invoice or bill.",
    )
    source_id = models.PositiveIntegerField(help_text="ID of the Invoice or Bill being paid.")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    payment_date = models.DateField()
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        help_text="Cash/bank account used to fund the payment.",
    )
    is_credit_adjustment = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]

    def __str__(self) -> str:
        return f"Payment {self.id} ({self.source_type}) {self.amount} on {self.payment_date}"

    def clean(self) -> None:
        if self.account.entity_id != self.entity_id:
            raise ValidationError({"account": "Account must belong to the same entity."})
        if not self.account.is_active:
            raise ValidationError({"account": "Account must be active."})


class PaymentApplication(models.Model):
    """Application of a payment to an invoice or bill."""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="applications")
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payment_applications",
        help_text="Invoice being paid, if applicable.",
    )
    bill = models.ForeignKey(
        Bill,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="payment_applications",
        help_text="Bill being paid, if applicable.",
    )
    applied_amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(check=Q(applied_amount__gt=0), name="payment_application_positive_amount"),
        ]

    def __str__(self) -> str:
        target = self.invoice or self.bill
        return f"Application {self.id}: {self.applied_amount} to {target}"

    def clean(self) -> None:
        if not self.invoice and not self.bill:
            raise ValidationError("Payment application must reference either an invoice or a bill.")
        if self.invoice and self.bill:
            raise ValidationError("Payment application cannot reference both invoice and bill.")
        if self.applied_amount <= Decimal("0.00"):
            raise ValidationError({"applied_amount": "Applied amount must be positive."})
        if self.applied_amount > self.payment.amount:
            raise ValidationError(
                {"applied_amount": f"Applied amount cannot exceed payment amount of {self.payment.amount}."}
            )


class CreditMemo(models.Model):
    """Credit memo for customer credits or vendor credits."""

    class Type(models.TextChoices):
        CUSTOMER = "customer", "Customer Credit"
        VENDOR = "vendor", "Vendor Credit"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="credit_memos")
    type = models.CharField(max_length=16, choices=Type.choices)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="credit_memos",
        help_text="Customer for customer credits.",
    )
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="credit_memos",
        help_text="Vendor for vendor credits.",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    memo_date = models.DateField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-memo_date", "-id"]

    def __str__(self) -> str:
        target = self.customer or self.vendor
        return f"Credit Memo {self.id}: {self.amount} for {target}"

    def clean(self) -> None:
        if not self.customer and not self.vendor:
            raise ValidationError("Credit memo must reference either a customer or a vendor.")
        if self.customer and self.vendor:
            raise ValidationError("Credit memo cannot reference both customer and vendor.")
        if self.customer and self.customer.entity_id != self.entity_id:
            raise ValidationError({"customer": "Customer must belong to the same entity."})
        if self.vendor and self.vendor.entity_id != self.entity_id:
            raise ValidationError({"vendor": "Vendor must belong to the same entity."})
