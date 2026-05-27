from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, Sum

from .accounts import Account, Entity
from .periods import AccountingPeriod
from apps.accounting.transition_rules import validate_journal_entry_status_transition


class JournalEntry(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        POSTED = "posted", "Posted"
        REVERSED = "reversed", "Reversed"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="journal_entries")
    date = models.DateField()
    description = models.TextField()
    period = models.ForeignKey(AccountingPeriod, on_delete=models.PROTECT, related_name="journal_entries", null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    source = models.CharField(max_length=64, default="manual")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="created_journal_entries")
    posted_at = models.DateTimeField(null=True, blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="reversed_journal_entries")
    reversal_of = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="reversal_entries")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]
        permissions = [
            (
                "post_soft_closed_journal_entries",
                "Can post journal entries in soft-closed periods",
            )
        ]

    def __str__(self) -> str:
        return f"JE-{self.id or 'new'} {self.date} {self.status}"

    @classmethod
    def ledger_affecting_statuses(cls) -> tuple[str, ...]:
        # Reversed originals still remain part of the historical ledger; the reversing posted entry offsets them.
        return (cls.Status.POSTED, cls.Status.REVERSED)

    @property
    def total_debits(self) -> Decimal:
        return self.lines.filter(side=JournalLine.Side.DEBIT).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    @property
    def total_credits(self) -> Decimal:
        return self.lines.filter(side=JournalLine.Side.CREDIT).aggregate(total=Sum("amount"))["total"] or Decimal("0.00")

    def assert_balanced(self) -> None:
        if self.total_debits != self.total_credits:
            raise ValidationError("Journal entry must balance: total debits must equal total credits.")
        if self.total_debits == Decimal("0.00"):
            raise ValidationError("Journal entry must include non-zero debit and credit totals.")

    def assert_mutable(self) -> None:
        if self.status != self.Status.DRAFT:
            raise ValidationError("Only draft journal entries may be edited destructively.")

    def clean(self) -> None:
        if self.pk:
            original_status = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            validate_journal_entry_status_transition(original_status=original_status, desired_status=self.status)
        elif self.status not in {self.Status.DRAFT, self.Status.POSTED}:
            raise ValidationError("Journal entries must be created as drafts or posted entries.")
        if self.pk and self.lines.exists():
            self.assert_balanced()

    def delete(self, *args: Any, **kwargs: Any):
        self.assert_mutable()
        return super().delete(*args, **kwargs)


class JournalLine(models.Model):
    class Side(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.CASCADE, related_name="lines")
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="lines")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    side = models.CharField(max_length=8, choices=Side.choices)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(check=Q(amount__gt=0), name="journal_line_positive_amount")]

    def clean(self) -> None:
        if self.journal_entry_id and self.account_id and self.journal_entry.entity_id != self.account.entity_id:
            raise ValidationError("Journal lines cannot use accounts from another entity.")

    def __str__(self) -> str:
        return f"{self.side} {self.amount} {self.account}"
