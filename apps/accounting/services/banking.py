from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounting.models import (
    Account,
    BankAccount,
    BankReconciliation,
    BankReconciliationMatch,
    BankStatementLine,
    BankTransaction,
)
from apps.accounting.selectors.banking import bank_account_balance
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.posting import JournalLineInput, create_and_post_journal_entry

MONEY_QUANT = Decimal("0.01")


def money(value: Decimal | str) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT)


@transaction.atomic
def save_bank_account(
    *,
    bank_account: BankAccount | None = None,
    entity=None,
    name: str,
    account_number: str,
    bank_name: str,
    ledger_account: Account,
    status: str = BankAccount.Status.ACTIVE,
    user=None,
    source: str = "manual",
) -> BankAccount:
    entity = entity or get_default_entity()
    if bank_account is None:
        bank_account = BankAccount(
            entity=entity,
            name=name,
            account_number=account_number,
            bank_name=bank_name,
            ledger_account=ledger_account,
            status=status,
        )
        audit_action = "bank_account_created"
        before = None
    else:
        before = {
            "name": bank_account.name,
            "account_number": bank_account.account_number,
            "bank_name": bank_account.bank_name,
            "ledger_account": bank_account.ledger_account_id,
            "status": bank_account.status,
        }
        bank_account.name = name
        bank_account.account_number = account_number
        bank_account.bank_name = bank_name
        bank_account.ledger_account = ledger_account
        bank_account.status = status
        if not bank_account.entity_id:
            bank_account.entity = entity
        audit_action = "bank_account_updated"

    bank_account.full_clean()
    bank_account.save()
    audit_success(
        action=audit_action,
        record=bank_account,
        user=user,
        source=source,
        metadata={
            "before": before,
            "after": {
                "name": bank_account.name,
                "account_number": bank_account.account_number,
                "bank_name": bank_account.bank_name,
                "ledger_account": bank_account.ledger_account_id,
                "status": bank_account.status,
            },
        },
    )
    return bank_account


@transaction.atomic
def record_bank_transaction(
    *,
    bank_account: BankAccount,
    transaction_date: date,
    amount: Decimal,
    transaction_type: str,
    offset_account: Account,
    memo: str = "",
    source_type: str = "manual",
    source_id: int | None = None,
    user=None,
    source: str = "manual",
) -> BankTransaction:
    if transaction_type not in BankTransaction.Type.values:
        raise ValidationError(f"Unsupported bank transaction type: {transaction_type}")
    amount = money(amount)
    if amount <= Decimal("0.00"):
        raise ValidationError({"amount": "Bank transaction amount must be positive."})

    line_amount = str(amount)
    if transaction_type == BankTransaction.Type.DEPOSIT:
        lines = [
            JournalLineInput(account_code=bank_account.ledger_account.account_code, side="debit", amount=line_amount, description=memo),
            JournalLineInput(account_code=offset_account.account_code, side="credit", amount=line_amount, description=memo),
        ]
    else:
        lines = [
            JournalLineInput(account_code=offset_account.account_code, side="debit", amount=line_amount, description=memo),
            JournalLineInput(account_code=bank_account.ledger_account.account_code, side="credit", amount=line_amount, description=memo),
        ]

    entry = create_and_post_journal_entry(
        entry_date=transaction_date,
        description=memo or f"{transaction_type.title()} for {bank_account.name}",
        lines=lines,
        created_by=user,
        source=source,
    )
    bank_transaction = BankTransaction(
        entity=bank_account.entity,
        bank_account=bank_account,
        journal_entry=entry,
        transaction_date=transaction_date,
        amount=amount,
        transaction_type=transaction_type,
        source_type=source_type,
        source_id=source_id,
        memo=memo,
    )
    bank_transaction.full_clean()
    bank_transaction.save()
    audit_success(
        action="bank_transaction_recorded",
        record=bank_transaction,
        user=user,
        source=source,
        metadata={
            "journal_entry_id": entry.id,
            "transaction_type": transaction_type,
            "amount": str(amount),
        },
    )
    return bank_transaction


@transaction.atomic
def create_bank_statement_line(
    *,
    bank_account: BankAccount,
    statement_date: date,
    amount: Decimal,
    description: str = "",
    statement_reference: str = "",
    user=None,
    source: str = "manual",
) -> BankStatementLine:
    statement_line = BankStatementLine(
        entity=bank_account.entity,
        bank_account=bank_account,
        statement_date=statement_date,
        amount=money(amount),
        description=description,
        statement_reference=statement_reference,
    )
    statement_line.full_clean()
    statement_line.save()
    audit_success(
        action="bank_statement_line_created",
        record=statement_line,
        user=user,
        source=source,
        metadata={"amount": str(statement_line.amount), "statement_reference": statement_reference},
    )
    return statement_line


@transaction.atomic
def create_bank_reconciliation(
    *,
    bank_account: BankAccount,
    start_date: date,
    end_date: date,
    statement_ending_balance: Decimal,
    user=None,
    source: str = "manual",
) -> BankReconciliation:
    reconciliation = BankReconciliation(
        entity=bank_account.entity,
        bank_account=bank_account,
        start_date=start_date,
        end_date=end_date,
        status=BankReconciliation.Status.OPEN,
        statement_ending_balance=money(statement_ending_balance),
        cleared_balance=Decimal("0.00"),
    )
    reconciliation.full_clean()
    reconciliation.save()
    audit_success(
        action="bank_reconciliation_created",
        record=reconciliation,
        user=user,
        source=source,
        metadata={"statement_ending_balance": str(reconciliation.statement_ending_balance)},
    )
    return reconciliation


@transaction.atomic
def match_bank_statement_line(
    *,
    reconciliation: BankReconciliation,
    statement_line: BankStatementLine,
    bank_transaction: BankTransaction,
    matched_amount: Decimal | None = None,
    user=None,
    source: str = "manual",
) -> BankReconciliationMatch:
    reconciliation = BankReconciliation.objects.select_for_update().get(pk=reconciliation.pk)
    if reconciliation.status != BankReconciliation.Status.OPEN:
        raise ValidationError("Only open bank reconciliations can be matched.")

    match = BankReconciliationMatch(
        reconciliation=reconciliation,
        statement_line=statement_line,
        bank_transaction=bank_transaction,
        matched_amount=money(matched_amount or abs(statement_line.amount)),
    )
    match.full_clean()
    match.save()
    audit_success(
        action="bank_reconciliation_match_created",
        record=match,
        user=user,
        source=source,
        metadata={
            "reconciliation_id": reconciliation.id,
            "statement_line_id": statement_line.id,
            "bank_transaction_id": bank_transaction.id,
            "matched_amount": str(match.matched_amount),
        },
    )
    return match


@transaction.atomic
def complete_bank_reconciliation(
    *,
    reconciliation: BankReconciliation,
    user=None,
    source: str = "manual",
) -> BankReconciliation:
    reconciliation = BankReconciliation.objects.select_for_update().get(pk=reconciliation.pk)
    if reconciliation.status != BankReconciliation.Status.OPEN:
        raise ValidationError("Only open bank reconciliations can be completed.")

    unresolved_lines = BankStatementLine.objects.filter(
        entity=reconciliation.entity,
        bank_account=reconciliation.bank_account,
        statement_date__range=(reconciliation.start_date, reconciliation.end_date),
    ).exclude(matches__reconciliation=reconciliation).distinct()
    if unresolved_lines.exists():
        raise ValidationError("All statement lines in the reconciliation period must be matched before completion.")

    book_balance = bank_account_balance(reconciliation.bank_account, as_of=reconciliation.end_date)
    if book_balance != reconciliation.statement_ending_balance:
        raise ValidationError(
            {
                "statement_ending_balance": "Statement ending balance must match the book balance to complete reconciliation.",
            }
        )

    reconciliation.cleared_balance = book_balance
    reconciliation.status = BankReconciliation.Status.COMPLETED
    reconciliation.save(update_fields=["cleared_balance", "status", "updated_at"])
    audit_success(
        action="bank_reconciliation_completed",
        record=reconciliation,
        user=user,
        source=source,
        metadata={
            "cleared_balance": str(reconciliation.cleared_balance),
            "statement_ending_balance": str(reconciliation.statement_ending_balance),
        },
    )
    return reconciliation
