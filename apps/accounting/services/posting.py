from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import Account, AccountingPeriod, JournalEntry, JournalLine
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity


@dataclass(frozen=True)
class JournalLineInput:
    account_code: str
    side: str
    amount: Decimal | str
    description: str = ""


def resolve_period_for_posting(entity, entry_date: date) -> AccountingPeriod:
    period = AccountingPeriod.find_for_date(entity, entry_date)
    if not period:
        raise ValidationError("No accounting period exists for the journal entry date.")
    return period


def validate_line_inputs(entity, lines: Iterable[JournalLineInput]) -> list[tuple[Account, str, Decimal, str]]:
    resolved: list[tuple[Account, str, Decimal, str]] = []
    for line in lines:
        if line.side not in JournalLine.Side.values:
            raise ValidationError(f"Invalid journal line side: {line.side}")
        amount = Decimal(str(line.amount)).quantize(Decimal("0.01"))
        if amount <= Decimal("0.00"):
            raise ValidationError("Journal line amounts must be positive.")
        try:
            account = Account.objects.get(entity=entity, account_code=line.account_code, is_active=True)
        except Account.DoesNotExist as exc:
            raise ValidationError(f"Active account not found for code {line.account_code}.") from exc
        resolved.append((account, line.side, amount, line.description))
    if len(resolved) < 2:
        raise ValidationError("A journal entry requires at least two lines.")
    return resolved


def assert_line_inputs_balanced(lines: Iterable[JournalLineInput]) -> None:
    total_debits = Decimal("0.00")
    total_credits = Decimal("0.00")
    for line in lines:
        if line.side == JournalLine.Side.DEBIT:
            total_debits += Decimal(str(line.amount))
        else:
            total_credits += Decimal(str(line.amount))
    if total_debits != total_credits:
        raise ValidationError("Journal entry must balance: total debits must equal total credits.")
    if total_debits == Decimal("0.00"):
        raise ValidationError("Journal entry must include non-zero debit and credit totals.")


@transaction.atomic
def create_draft_journal_entry(*, entry_date: date, description: str, lines: Iterable[JournalLineInput], created_by=None, source: str = "manual") -> JournalEntry:
    entity = get_default_entity()
    line_inputs = list(lines)
    resolved_lines = validate_line_inputs(entity, line_inputs)
    assert_line_inputs_balanced(line_inputs)
    period = resolve_period_for_posting(entity, entry_date)
    entry = JournalEntry.objects.create(
        entity=entity,
        date=entry_date,
        description=description,
        period=period,
        status=JournalEntry.Status.DRAFT,
        source=source,
        created_by=created_by,
    )
    JournalLine.objects.bulk_create(
        JournalLine(journal_entry=entry, account=account, side=side, amount=amount, description=line_description)
        for account, side, amount, line_description in resolved_lines
    )
    entry.refresh_from_db()
    entry.assert_balanced()
    audit_success(action="journal_entry_created", record=entry, user=created_by, source=source, metadata={"status": entry.status})
    return entry


@transaction.atomic
def update_draft_journal_entry(*, entry: JournalEntry, entry_date: date | None = None, description: str | None = None, lines: Iterable[JournalLineInput] | None = None, user=None, source: str = "manual") -> JournalEntry:
    entry.assert_mutable()
    before = {"date": str(entry.date), "description": entry.description, "line_count": entry.lines.count()}
    update_fields = ["updated_at"]
    if entry_date is not None:
        entry.date = entry_date
        entry.period = resolve_period_for_posting(entry.entity, entry_date)
        update_fields.extend(["date", "period"])
    if description is not None:
        entry.description = description
        update_fields.append("description")
    entry.save(update_fields=sorted(set(update_fields)))
    if lines is not None:
        line_inputs = list(lines)
        resolved_lines = validate_line_inputs(entry.entity, line_inputs)
        assert_line_inputs_balanced(line_inputs)
        entry.lines.all().delete()
        JournalLine.objects.bulk_create(
            JournalLine(journal_entry=entry, account=account, side=side, amount=amount, description=line_description)
            for account, side, amount, line_description in resolved_lines
        )
        entry.refresh_from_db()
        entry.assert_balanced()
    audit_success(
        action="journal_entry_updated",
        record=entry,
        user=user,
        source=source,
        metadata={"before": before, "after": {"date": str(entry.date), "description": entry.description, "line_count": entry.lines.count()}},
    )
    return entry


@transaction.atomic
def post_journal_entry(*, entry: JournalEntry, user=None, source: str | None = None, allow_soft_closed: bool = False) -> JournalEntry:
    entry = JournalEntry.objects.select_for_update().get(pk=entry.pk)
    if entry.status != JournalEntry.Status.DRAFT:
        raise ValidationError("Only draft journal entries can be posted.")
    period = resolve_period_for_posting(entry.entity, entry.date)
    period.assert_posting_allowed(allow_soft_closed=allow_soft_closed)
    entry.period = period
    entry.assert_balanced()
    entry.status = JournalEntry.Status.POSTED
    entry.posted_at = timezone.now()
    entry.save(update_fields=["status", "posted_at", "period", "updated_at"])
    audit_success(
        action="journal_entry_posted",
        record=entry,
        user=user or entry.created_by,
        source=source or entry.source,
        metadata={"total_debits": str(entry.total_debits), "total_credits": str(entry.total_credits)},
    )
    return entry


@transaction.atomic
def create_and_post_journal_entry(*, entry_date: date, description: str, lines: Iterable[JournalLineInput], created_by=None, source: str = "manual", allow_soft_closed: bool = False) -> JournalEntry:
    entry = create_draft_journal_entry(entry_date=entry_date, description=description, lines=lines, created_by=created_by, source=source)
    return post_journal_entry(entry=entry, user=created_by, source=source, allow_soft_closed=allow_soft_closed)
