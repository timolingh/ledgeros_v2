from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .accounts import Account, Entity


class ReportView(models.Model):
    class ReportType(models.TextChoices):
        BALANCE_SHEET = "balance_sheet", "Balance Sheet"
        PROFIT_AND_LOSS = "profit_and_loss", "Profit and Loss"

    class Basis(models.TextChoices):
        ACCRUAL = "accrual", "Accrual"
        CASH = "cash", "Cash"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="report_views")
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=32, choices=ReportType.choices)
    basis = models.CharField(max_length=16, choices=Basis.choices, default=Basis.ACCRUAL)
    as_of_date = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    filters = models.JSONField(default=dict, blank=True)
    display_settings = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="created_report_views",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["entity", "name"], name="unique_report_view_name_per_entity"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.report_type})"

    def clean(self) -> None:
        if self.report_type == self.ReportType.BALANCE_SHEET:
            if not self.as_of_date:
                raise ValidationError({"as_of_date": "Balance sheet report views require an as_of_date."})
            if self.start_date or self.end_date:
                raise ValidationError("Balance sheet report views must not set start or end dates.")
            if self.basis != self.Basis.ACCRUAL:
                raise ValidationError({"basis": "Balance sheet reporting supports accrual basis only in Epic 4."})
        elif self.report_type == self.ReportType.PROFIT_AND_LOSS:
            if not self.start_date or not self.end_date:
                raise ValidationError("Profit and loss report views require both start_date and end_date.")
            if self.start_date > self.end_date:
                raise ValidationError({"end_date": "End date must be on or after the start date."})
        else:
            raise ValidationError({"report_type": "Unsupported report type."})

        if self.filters is None:
            self.filters = {}
        if self.display_settings is None:
            self.display_settings = {}


class TaxCode(models.Model):
    class Jurisdiction(models.TextChoices):
        US = "us", "United States"
        CA = "ca", "California"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="tax_codes")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    rate = models.DecimalField(max_digits=7, decimal_places=4, help_text="Tax rate expressed as a decimal fraction.")
    jurisdiction = models.CharField(max_length=16, choices=Jurisdiction.choices, default=Jurisdiction.US)
    liability_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="tax_codes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["code", "id"]
        constraints = [
            models.UniqueConstraint(fields=["entity", "code"], name="unique_tax_code_per_entity"),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.name}"

    def clean(self) -> None:
        if self.liability_account.entity_id != self.entity_id:
            raise ValidationError({"liability_account": "Tax liability account must belong to the same entity."})
        if self.liability_account.type != Account.AccountType.LIABILITY:
            raise ValidationError({"liability_account": "Tax liability account must be a liability account."})
        if not self.liability_account.is_active:
            raise ValidationError({"liability_account": "Tax liability account must be active."})
        if self.rate < Decimal("0.0000"):
            raise ValidationError({"rate": "Tax rate must be non-negative."})
