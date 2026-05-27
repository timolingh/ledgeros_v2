from datetime import date
from types import SimpleNamespace

import pytest
from django.contrib import admin as django_admin
from django.core.exceptions import ValidationError
from django.forms.models import inlineformset_factory
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.accounting.admin import AccountAdmin, AccountingPeriodAdmin, JournalEntryAdmin, JournalLineInlineFormSet
from apps.accounting.models import Account, AccountingPeriod, AuditLog, Entity, JournalEntry, JournalLine
from apps.accounting.services import JournalLineInput, create_accounting_period, create_and_post_journal_entry, create_draft_journal_entry, post_journal_entry, update_draft_journal_entry
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
def test_unbalanced_draft_cannot_be_created(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    with pytest.raises(ValidationError):
        create_draft_journal_entry(
            entry_date=date(2026, 5, 1),
            description="Unbalanced draft",
            lines=[
                JournalLineInput(account_code="1000", side="debit", amount="100.00"),
                JournalLineInput(account_code="4000", side="credit", amount="99.00"),
            ],
        )


@pytest.mark.django_db
def test_unbalanced_draft_update_is_rejected(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Draft cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )

    with pytest.raises(ValidationError):
        update_draft_journal_entry(
            entry=draft,
            lines=[
                JournalLineInput(account_code="1000", side="debit", amount="100.00"),
                JournalLineInput(account_code="4000", side="credit", amount="99.00"),
            ],
        )


@pytest.mark.django_db
def test_draft_entries_may_be_edited(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Draft cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )

    updated = update_draft_journal_entry(
        entry=draft,
        description="Updated draft cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="120.00"),
            JournalLineInput(account_code="4000", side="credit", amount="120.00"),
        ],
    )
    updated.refresh_from_db()

    assert updated.status == JournalEntry.Status.DRAFT
    assert updated.description == "Updated draft cash sale"
    assert updated.total_debits == updated.total_credits == 120
    assert AuditLog.objects.filter(action="journal_entry_updated", record_id=str(updated.pk)).exists()


@pytest.mark.django_db
def test_posted_entries_cannot_be_edited(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    entry = create_and_post_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )

    with pytest.raises(ValidationError):
        update_draft_journal_entry(entry=entry, description="Should fail")


@pytest.mark.django_db
def test_unsaved_journal_entry_full_clean_does_not_query_lines(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    entry = JournalEntry(
        entity=coa,
        date=date(2026, 5, 1),
        description="Draft entry shell",
        status=JournalEntry.Status.DRAFT,
        source="manual",
    )

    entry.full_clean()


@pytest.mark.django_db
def test_direct_status_change_is_rejected_by_model_validation(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Draft entry",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )

    draft.status = JournalEntry.Status.POSTED

    with pytest.raises(ValidationError) as exc_info:
        draft.full_clean()

    assert "posting or reversal services" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_reversed_entries_cannot_be_edited(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    draft = create_draft_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )
    post_journal_entry(entry=draft)
    draft.refresh_from_db()
    draft.status = JournalEntry.Status.REVERSED
    draft.save(update_fields=["status", "updated_at"])

    with pytest.raises(ValidationError):
        update_draft_journal_entry(entry=draft, description="Should fail")


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
def test_create_and_post_journal_entry_rejects_soft_closed_period_without_override(coa):
    period = create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    period.mark_soft_closed()

    with pytest.raises(ValidationError) as exc_info:
        create_and_post_journal_entry(
            entry_date=date(2026, 5, 1),
            description="Soft closed period entry",
            lines=[
                JournalLineInput(account_code="1000", side="debit", amount="100.00"),
                JournalLineInput(account_code="4000", side="credit", amount="100.00"),
            ],
        )

    assert "soft-closed accounting periods require elevated approval for posting" in str(exc_info.value).lower()


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
    with pytest.raises(ValidationError):
        create_draft_journal_entry(
            entry_date=date(2026, 5, 1),
            description="Bad entry",
            lines=[
                JournalLineInput(account_code="1000", side="debit", amount="100.00"),
                JournalLineInput(account_code="4000", side="credit", amount="99.00"),
            ],
        )

    assert AuditLog.objects.count() == before
    assert not AuditLog.objects.filter(action="journal_entry_created").exists()


@pytest.mark.django_db
def test_successful_actions_create_audit_logs(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    assert AuditLog.objects.filter(action="chart_of_accounts_imported").exists()
    assert AuditLog.objects.filter(action="period_created").exists()


@pytest.mark.django_db
def test_admin_inline_formset_rejects_unbalanced_journal_entry(coa):
    period = create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    entry = JournalEntry.objects.create(
        entity=coa,
        date=date(2026, 5, 1),
        description="Admin draft",
        period=period,
        status=JournalEntry.Status.DRAFT,
        source="manual",
    )

    formset_class = inlineformset_factory(JournalEntry, JournalLine, fields=("account", "side", "amount", "description"), extra=0, formset=JournalLineInlineFormSet)
    data = {
        "lines-TOTAL_FORMS": "2",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-account": str(Account.objects.get(account_code="1000").pk),
        "lines-0-side": JournalLine.Side.DEBIT,
        "lines-0-amount": "100.00",
        "lines-0-description": "",
        "lines-1-account": str(Account.objects.get(account_code="4000").pk),
        "lines-1-side": JournalLine.Side.CREDIT,
        "lines-1-amount": "99.00",
        "lines-1-description": "",
    }
    formset = formset_class(data=data, instance=entry, prefix="lines")

    assert not formset.is_valid()
    assert formset.non_form_errors()
    assert "Journal entry must balance" in str(formset.non_form_errors())


@pytest.mark.django_db
def test_journal_entry_admin_save_related_uses_shared_update_service(coa):
    period = create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    entry = JournalEntry.objects.create(
        entity=coa,
        date=date(2026, 5, 1),
        description="Admin draft",
        period=period,
        status=JournalEntry.Status.DRAFT,
        source="manual",
    )
    request = RequestFactory().get("/admin/")
    request.user = get_user_model().objects.create_superuser(username="admin-save", password="password", email="admin-save@example.com")
    admin_instance = JournalEntryAdmin(JournalEntry, django_admin.site)
    form = SimpleNamespace(instance=entry, cleaned_data={"date": entry.date, "description": entry.description})
    formset_class = inlineformset_factory(JournalEntry, JournalLine, fields=("account", "side", "amount", "description"), extra=0, formset=JournalLineInlineFormSet)
    formset = formset_class(
        data={
            "lines-TOTAL_FORMS": "2",
            "lines-INITIAL_FORMS": "0",
            "lines-MIN_NUM_FORMS": "0",
            "lines-MAX_NUM_FORMS": "1000",
            "lines-0-account": str(Account.objects.get(account_code="1000").pk),
            "lines-0-side": JournalLine.Side.DEBIT,
            "lines-0-amount": "100.00",
            "lines-0-description": "",
            "lines-1-account": str(Account.objects.get(account_code="4000").pk),
            "lines-1-side": JournalLine.Side.CREDIT,
            "lines-1-amount": "100.00",
            "lines-1-description": "",
        },
        instance=entry,
        prefix="lines",
    )

    assert formset.is_valid()
    admin_instance.save_related(request, form, [formset], change=False)
    entry.refresh_from_db()

    assert entry.lines.count() == 2
    assert AuditLog.objects.filter(action="journal_entry_created", record_id=str(entry.pk)).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    "admin_class, model_class, model_kwargs",
    [
        (
            AccountAdmin,
            Account,
            {"account_code": "5000", "name": "Other Income", "type": Account.AccountType.REVENUE, "normal_balance": Account.NormalBalance.CREDIT},
        ),
        (
            AccountingPeriodAdmin,
            AccountingPeriod,
            {"name": "FY2027", "start_date": date(2027, 1, 1), "end_date": date(2027, 12, 31)},
        ),
        (
            JournalEntryAdmin,
            JournalEntry,
            {"date": date(2026, 5, 1), "description": "Admin entry", "period": None, "status": JournalEntry.Status.DRAFT, "source": "manual"},
        ),
    ],
)
def test_admin_forms_hide_entity_and_assign_default_entity(coa, admin_class, model_class, model_kwargs):
    request = RequestFactory().get("/admin/")
    request.user = get_user_model().objects.create_superuser(username="admin", password="password", email="admin@example.com")
    admin_instance = admin_class(model_class, django_admin.site)

    form_class = admin_instance.get_form(request)
    assert "entity" not in form_class.base_fields
    if admin_class is JournalEntryAdmin:
        assert "status" not in form_class.base_fields
        assert "posted_at" not in form_class.base_fields
        assert "reversed_at" not in form_class.base_fields
        assert "reversal_of" not in form_class.base_fields
    if admin_class is AccountingPeriodAdmin:
        assert "status" not in form_class.base_fields
        assert "closed_at" not in form_class.base_fields
        assert "locked_at" not in form_class.base_fields

    entity = get_default_entity()
    if admin_class is JournalEntryAdmin:
        period = create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
        model_kwargs = {**model_kwargs, "period": period}
    obj = model_class(entity=None, **model_kwargs)

    admin_instance.save_model(request, obj, form=None, change=False)
    obj.refresh_from_db()
    assert obj.entity == entity


@pytest.mark.django_db
def test_account_admin_shows_posted_balance(coa):
    create_accounting_period(start_date=date(2026, 1, 1), end_date=date(2026, 12, 31), name="FY2026")
    create_and_post_journal_entry(
        entry_date=date(2026, 5, 1),
        description="Cash sale",
        lines=[
            JournalLineInput(account_code="1000", side="debit", amount="100.00"),
            JournalLineInput(account_code="4000", side="credit", amount="100.00"),
        ],
    )

    request = RequestFactory().get("/admin/")
    request.user = get_user_model().objects.create_superuser(username="balance-admin", password="password", email="balance-admin@example.com")
    admin_instance = AccountAdmin(Account, django_admin.site)
    assert "posted_balance" in admin_instance.get_list_display(request=request)
    assert "posted_balance" in admin_instance.get_readonly_fields(request=request)
    assert admin_instance.posted_balance(Account.objects.get(account_code="1000")) == 100


@pytest.mark.django_db
def test_entity_is_not_registered_in_admin():
    assert Entity not in django_admin.site._registry
