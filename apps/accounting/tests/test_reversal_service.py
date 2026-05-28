from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import Account, AuditLog, JournalEntry
from apps.accounting.selectors import account_balance
from apps.accounting.services import JournalLineInput, create_accounting_period, create_and_post_journal_entry, reverse_journal_entry
from apps.accounting.services.chart_import import import_chart_of_accounts
from apps.accounting.services.entities import get_default_entity


@pytest.fixture
def accounting_ready(tmp_path):
    entity = get_default_entity()
    path = tmp_path / "coa.yml"
    path.write_text(
        """accounts:
  - code: "1000"
    name: Cash
    type: asset
    normal_balance: debit
  - code: "4000"
    name: Revenue
    type: revenue
    normal_balance: credit
""",
        encoding="utf-8",
    )
    import_chart_of_accounts(path=path, entity=entity)
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")


@pytest.mark.django_db
def test_reversal_offsets_posted_balances(accounting_ready):
    entry = create_and_post_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    reversal = reverse_journal_entry(entry=entry, reversal_date=date(2026, 5, 2))
    entry.refresh_from_db()
    assert entry.status == JournalEntry.Status.REVERSED
    assert reversal.status == JournalEntry.Status.POSTED
    assert reversal.reversal_of == entry
    assert entry.lines.count() == 2
    assert account_balance(Account.objects.get(account_code="1000")) == 0
    assert account_balance(Account.objects.get(account_code="4000")) == 0
    assert AuditLog.objects.filter(action="journal_entry_reversed", record_id=str(entry.pk)).exists()


@pytest.mark.django_db
def test_cannot_reverse_a_reversal(accounting_ready):
    entry = create_and_post_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    reversal = reverse_journal_entry(entry=entry, reversal_date=date(2026, 5, 2))

    with pytest.raises(ValidationError, match="Reversal entries cannot be reversed"):
        reverse_journal_entry(entry=reversal, reversal_date=date(2026, 5, 3))
