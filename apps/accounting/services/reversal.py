from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounting.models import JournalEntry, JournalLine
from apps.accounting.services.audit import audit_success
from apps.accounting.services.posting import JournalLineInput, create_and_post_journal_entry


@transaction.atomic
def reverse_journal_entry(*, entry: JournalEntry, reversal_date: date, user=None, source: str = "manual", description: str | None = None, allow_soft_closed: bool = False) -> JournalEntry:
    original = JournalEntry.objects.select_for_update().get(pk=entry.pk)
    if original.status != JournalEntry.Status.POSTED:
        raise ValidationError("Only posted journal entries can be reversed.")
    if original.reversal_of is not None:
        raise ValidationError("Reversal entries cannot be reversed.")
    reversal_lines = [
        JournalLineInput(
            account_code=line.account.account_code,
            side=JournalLine.Side.CREDIT if line.side == JournalLine.Side.DEBIT else JournalLine.Side.DEBIT,
            amount=line.amount,
            description=f"Reversal of line {line.id}",
        )
        for line in original.lines.select_related("account")
    ]
    reversal = create_and_post_journal_entry(
        entry_date=reversal_date,
        description=description or f"Reversal of journal entry {original.pk}",
        lines=reversal_lines,
        created_by=user,
        source=source,
        allow_soft_closed=allow_soft_closed,
    )
    reversal.reversal_of = original
    reversal.save(update_fields=["reversal_of", "updated_at"])
    original.status = JournalEntry.Status.REVERSED
    original.reversed_at = timezone.now()
    original.reversed_by = user
    original.save(update_fields=["status", "reversed_at", "reversed_by", "updated_at"])
    audit_success(
        action="journal_entry_reversed",
        record=original,
        user=user,
        source=source,
        metadata={"reversal_entry_id": reversal.pk},
    )
    return reversal
