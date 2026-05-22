from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.accounting.models import Account, AccountingPeriod, AuditLog, JournalEntry
from apps.accounting.services import JournalLineInput, create_accounting_period, create_and_post_journal_entry, create_draft_journal_entry, post_journal_entry
from apps.accounting.services.chart_import import import_chart_of_accounts
from apps.accounting.services.entities import get_default_entity


@pytest.fixture
def entity():
    return get_default_entity()


@pytest.fixture
def coa(tmp_path, entity):
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
    return entity


@pytest.mark.django_db
def test_draft_does_not_affect_balances(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Draft cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    assert draft.status == JournalEntry.Status.DRAFT
    assert Account.objects.get(account_code="1000").posted_balance() == 0


@pytest.mark.django_db
def test_post_balanced_entry_changes_balances(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    entry = create_and_post_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    assert entry.status == JournalEntry.Status.POSTED
    assert Account.objects.get(account_code="1000").posted_balance() == 100
    assert Account.objects.get(account_code="4000").posted_balance() == 100


@pytest.mark.django_db
def test_unbalanced_entry_cannot_post(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Bad entry",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="99.00"),
        ],
    )
    with pytest.raises(ValidationError):
        post_journal_entry(entry=draft)


@pytest.mark.django_db
def test_locked_period_rejects_posting(coa):
    period = create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    period.status = AccountingPeriod.Status.LOCKED
    period.save(update_fields=["status", "updated_at"])
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Locked period entry",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    with pytest.raises(ValidationError):
        post_journal_entry(entry=draft)


@pytest.mark.django_db
def test_successful_actions_create_audit_logs(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    assert AuditLog.objects.filter(action="chart_of_accounts_imported").exists()
    assert AuditLog.objects.filter(action="period_created").exists()
