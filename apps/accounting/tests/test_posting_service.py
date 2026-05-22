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
def test_valid_chart_of_accounts_import_succeeds(tmp_path, entity):
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

    result = import_chart_of_accounts(path=path, entity=entity)

    assert result.created == 2
    assert result.updated == 0
    assert result.unchanged == 0
    assert Account.objects.filter(entity=entity, account_code="1000", name="Cash").exists()
    assert Account.objects.filter(entity=entity, account_code="4000", name="Revenue").exists()


@pytest.mark.django_db
def test_invalid_normal_balance_in_chart_of_accounts_fails(tmp_path, entity):
    path = tmp_path / "coa.yml"
    path.write_text(
        """accounts:
  - code: "1000"
    name: Cash
    type: asset
    normal_balance: credit
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        import_chart_of_accounts(path=path, entity=entity)


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
    assert AuditLog.objects.filter(action="journal_entry_posted", record_id=str(entry.pk)).exists()


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
def test_soft_closed_period_rejects_posting(coa):
    period = create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    period.mark_soft_closed()
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Soft closed period entry",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
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
def test_inactive_account_rejects_journal_entry_creation(coa):
    account = Account.objects.get(account_code="1000")
    account.is_active = False
    account.save(update_fields=["is_active", "updated_at"])
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")

    with pytest.raises(ValidationError):
        create_draft_journal_entry(
            entry_date=date(2026, 5, 1),
            description="Inactive account entry",
            lines=[
                JournalLineInput(account_code="1000", side="debit", amount="100.00"),
                JournalLineInput(account_code="4000", side="credit", amount="100.00"),
            ],
        )


@pytest.mark.django_db
def test_failed_validations_do_not_create_audit_logs(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    before = AuditLog.objects.count()
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

    assert AuditLog.objects.count() == before + 1
    assert not AuditLog.objects.filter(action="journal_entry_posted").exists()


@pytest.mark.django_db
def test_successful_actions_create_audit_logs(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    assert AuditLog.objects.filter(action="chart_of_accounts_imported").exists()
    assert AuditLog.objects.filter(action="period_created").exists()
