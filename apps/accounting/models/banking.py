from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from .accounts import Account, Entity


class BankAccount(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="bank_accounts")
    name = models.CharField(max_length=255)
    account_number = models.CharField(max_length=64)
    bank_name = models.CharField(max_length=255)
    ledger_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name="bank_accounts")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "account_number"],
                condition=Q(account_number__gt=""),
                name="unique_bank_account_number_per_entity",
            ),
        ]
        ordering = ["name", "id"]

    def __str__(self) -> str:
        return f"{self.bank_name} - {self.name}"

    def clean(self) -> None:
        if self.ledger_account.entity_id != self.entity_id:
            raise ValidationError({"ledger_account": "Ledger account must belong to the same entity."})
        if self.ledger_account.type != Account.AccountType.ASSET:
            raise ValidationError({"ledger_account": "Bank accounts must link to an asset account."})
        if self.ledger_account.normal_balance != Account.NormalBalance.DEBIT:
            raise ValidationError({"ledger_account": "Bank accounts must link to a debit-normal account."})
        if not self.ledger_account.is_active:
            raise ValidationError({"ledger_account": "Ledger account must be active."})

    def current_balance(self) -> Decimal:
        from apps.accounting.selectors.banking import bank_account_balance

        return bank_account_balance(self)


class BankTransaction(models.Model):
    class Type(models.TextChoices):
        DEPOSIT = "deposit", "Deposit"
        WITHDRAWAL = "withdrawal", "Withdrawal"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="bank_transactions")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="transactions")
    journal_entry = models.ForeignKey(
        "JournalEntry",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="bank_transactions",
    )
    transaction_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_type = models.CharField(max_length=16, choices=Type.choices)
    source_type = models.CharField(max_length=64, blank=True)
    source_id = models.PositiveIntegerField(null=True, blank=True)
    memo = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-transaction_date", "-id"]

    def __str__(self) -> str:
        return f"{self.bank_account.name} {self.transaction_type} {self.amount}"

    @property
    def signed_amount(self) -> Decimal:
        if self.transaction_type == self.Type.DEPOSIT:
            return self.amount
        return Decimal("0.00") - self.amount

    def clean(self) -> None:
        if self.bank_account.entity_id != self.entity_id:
            raise ValidationError({"bank_account": "Bank account must belong to the same entity."})
        if self.journal_entry and self.journal_entry.entity_id != self.entity_id:
            raise ValidationError({"journal_entry": "Journal entry must belong to the same entity."})
        if self.amount <= Decimal("0.00"):
            raise ValidationError({"amount": "Bank transaction amount must be positive."})


class BankStatementLine(models.Model):
    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="bank_statement_lines")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="statement_lines")
    statement_date = models.DateField()
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    statement_reference = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "bank_account", "statement_reference"],
                condition=Q(statement_reference__gt=""),
                name="unique_bank_statement_reference_per_account",
            ),
        ]
        ordering = ["-statement_date", "-id"]

    def __str__(self) -> str:
        return f"{self.bank_account.name} statement line {self.amount}"

    def clean(self) -> None:
        if self.bank_account.entity_id != self.entity_id:
            raise ValidationError({"bank_account": "Bank account must belong to the same entity."})
        if self.amount == Decimal("0.00"):
            raise ValidationError({"amount": "Statement line amount cannot be zero."})


class BankReconciliation(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        COMPLETED = "completed", "Completed"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="bank_reconciliations")
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name="reconciliations")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    statement_ending_balance = models.DecimalField(max_digits=14, decimal_places=2)
    cleared_balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-end_date", "-id"]

    def __str__(self) -> str:
        return f"Reconciliation {self.bank_account.name} {self.start_date} to {self.end_date}"

    def clean(self) -> None:
        if self.bank_account.entity_id != self.entity_id:
            raise ValidationError({"bank_account": "Bank account must belong to the same entity."})
        if self.start_date > self.end_date:
            raise ValidationError({"end_date": "End date must be on or after the start date."})


class BankReconciliationMatch(models.Model):
    reconciliation = models.ForeignKey(BankReconciliation, on_delete=models.CASCADE, related_name="matches")
    statement_line = models.ForeignKey(BankStatementLine, on_delete=models.CASCADE, related_name="matches")
    bank_transaction = models.ForeignKey(BankTransaction, on_delete=models.CASCADE, related_name="reconciliation_matches")
    matched_amount = models.DecimalField(max_digits=14, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["statement_line"], name="unique_statement_line_match"),
            models.UniqueConstraint(fields=["bank_transaction"], name="unique_bank_transaction_match"),
        ]
        ordering = ["id"]

    def __str__(self) -> str:
        return f"Match {self.statement_line_id} -> {self.bank_transaction_id}"

    def clean(self) -> None:
        if self.reconciliation.bank_account_id != self.statement_line.bank_account_id:
            raise ValidationError({"statement_line": "Statement line must belong to the reconciliation bank account."})
        if self.reconciliation.bank_account_id != self.bank_transaction.bank_account_id:
            raise ValidationError({"bank_transaction": "Bank transaction must belong to the reconciliation bank account."})
        if self.reconciliation.entity_id != self.statement_line.entity_id or self.reconciliation.entity_id != self.bank_transaction.entity_id:
            raise ValidationError("Reconciliation matches must stay within the same entity.")
        if not (self.reconciliation.start_date <= self.statement_line.statement_date <= self.reconciliation.end_date):
            raise ValidationError({"statement_line": "Statement line date must fall within the reconciliation period."})
        if not (self.reconciliation.start_date <= self.bank_transaction.transaction_date <= self.reconciliation.end_date):
            raise ValidationError({"bank_transaction": "Bank transaction date must fall within the reconciliation period."})
        if self.matched_amount <= Decimal("0.00"):
            raise ValidationError({"matched_amount": "Matched amount must be positive."})
        if self.bank_transaction.transaction_type == BankTransaction.Type.DEPOSIT and self.statement_line.amount <= Decimal("0.00"):
            raise ValidationError({"statement_line": "Deposit transactions require a positive statement line amount."})
        if self.bank_transaction.transaction_type == BankTransaction.Type.WITHDRAWAL and self.statement_line.amount >= Decimal("0.00"):
            raise ValidationError({"statement_line": "Withdrawal transactions require a negative statement line amount."})
        if self.statement_line.amount != self.bank_transaction.signed_amount:
            raise ValidationError({"statement_line": "Statement line amount must match the bank transaction signed amount."})
        if self.matched_amount != self.bank_transaction.amount:
            raise ValidationError({"matched_amount": "Matched amount must equal the bank transaction amount."})
