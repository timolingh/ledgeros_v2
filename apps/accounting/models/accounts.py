from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class Entity(models.Model):
    """Hidden default entity for the MVP, with a schema path to future multi-entity support."""

    name = models.CharField(max_length=255, default="Default Entity")
    slug = models.SlugField(max_length=64, unique=True, default="default")
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["is_default"],
                condition=Q(is_default=True),
                name="one_default_entity",
            )
        ]
        ordering = ["id"]

    def __str__(self) -> str:
        return self.name

    @classmethod
    def get_default(cls) -> "Entity":
        entity, _ = cls.objects.get_or_create(
            slug="default",
            defaults={"name": "Default Entity", "is_default": True},
        )
        if not entity.is_default:
            entity.is_default = True
            entity.save(update_fields=["is_default"])
        return entity


class Account(models.Model):
    class AccountType(models.TextChoices):
        ASSET = "asset", "Asset"
        LIABILITY = "liability", "Liability"
        EQUITY = "equity", "Equity"
        REVENUE = "revenue", "Revenue"
        EXPENSE = "expense", "Expense"

    class NormalBalance(models.TextChoices):
        DEBIT = "debit", "Debit"
        CREDIT = "credit", "Credit"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="accounts")
    account_code = models.CharField(max_length=32)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=32, choices=AccountType.choices)
    normal_balance = models.CharField(max_length=8, choices=NormalBalance.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["entity", "account_code"], name="unique_account_code_per_entity"),
            models.CheckConstraint(
                check=Q(normal_balance__in=["debit", "credit"]),
                name="valid_account_normal_balance",
            ),
        ]
        ordering = ["account_code"]

    def __str__(self) -> str:
        return f"{self.account_code} - {self.name}"

    @staticmethod
    def expected_normal_balance(account_type: str) -> str:
        if account_type in {Account.AccountType.ASSET, Account.AccountType.EXPENSE}:
            return Account.NormalBalance.DEBIT
        return Account.NormalBalance.CREDIT

    def clean(self) -> None:
        expected = self.expected_normal_balance(self.type)
        if self.normal_balance != expected:
            raise ValidationError({"normal_balance": f"{self.type} accounts must normally be {expected}."})

    def posted_balance(self) -> Decimal:
        """Compatibility wrapper for callers that still ask the account directly.

        Balance calculation is owned by apps.accounting.selectors.balances so
        reporting/read-model logic has one canonical implementation.
        """

        from apps.accounting.selectors.balances import account_balance

        return account_balance(self)
