from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.db.utils import OperationalError
from rest_framework.test import APIClient

from apps.accounting.api.views import connection
from apps.accounting.models import Account, AccountingPeriod, AuditLog, JournalEntry
from apps.accounting.services import create_accounting_period
from apps.accounting.services.chart_import import import_chart_of_accounts
from apps.accounting.services.entities import get_default_entity


@pytest.fixture
def api_client(db):
    user = get_user_model().objects.create_user(username="tester", password="password")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


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


def create_draft_via_api(api_client):
    response = api_client.post(
        "/api/v1/journal-entries/",
        {
            "date": "2026-05-01",
            "description": "API cash sale",
            "lines": [
                {"account_code": "1000", "side": "debit", "amount": "100.00"},
                {"account_code": "4000", "side": "credit", "amount": "100.00"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    return response.data["id"]


@pytest.mark.django_db
def test_health_check_endpoint_is_available(api_client):
    response = api_client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.data == {"status": "ok"}


@pytest.mark.django_db
def test_health_check_endpoint_returns_unhealthy_on_database_error(api_client, monkeypatch):
    def raise_operational_error():
        raise OperationalError("db down")

    monkeypatch.setattr(connection, "ensure_connection", raise_operational_error)

    response = api_client.get("/api/v1/health/")

    assert response.status_code == 503
    assert response.data == {"status": "unhealthy"}


@pytest.mark.django_db
def test_create_and_post_journal_entry_via_api(api_client, accounting_ready):
    entry_id = create_draft_via_api(api_client)

    response = api_client.post(f"/api/v1/journal-entries/{entry_id}/post/", {}, format="json")

    assert response.status_code == 200
    assert response.data["status"] == "posted"


@pytest.mark.django_db
def test_one_line_journal_entry_via_api_is_rejected(api_client, accounting_ready):
    response = api_client.post(
        "/api/v1/journal-entries/",
        {
            "date": "2026-05-01",
            "description": "Invalid one-line entry",
            "lines": [
                {"account_code": "1000", "side": "debit", "amount": "100.00"},
            ],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "at least two lines" in str(response.data).lower()


@pytest.mark.django_db
def test_closed_period_rejects_posting_via_api(api_client, accounting_ready):
    period = AccountingPeriod.objects.get(name="FY2026")
    period.mark_closed()
    entry_id = create_draft_via_api(api_client)

    response = api_client.post(f"/api/v1/journal-entries/{entry_id}/post/", {}, format="json")

    assert response.status_code == 400
    assert "closed accounting periods reject postings" in str(response.data).lower()


@pytest.mark.django_db
def test_journal_entry_patch_updates_draft_only(api_client, accounting_ready):
    entry_id = create_draft_via_api(api_client)

    response = api_client.patch(
        f"/api/v1/journal-entries/{entry_id}/",
        {"description": "Updated draft from API"},
        format="json",
    )

    assert response.status_code == 200
    assert response.data["description"] == "Updated draft from API"
    assert response.data["status"] == JournalEntry.Status.DRAFT


@pytest.mark.django_db
def test_journal_entry_status_field_is_rejected_on_create(api_client, accounting_ready):
    response = api_client.post(
        "/api/v1/journal-entries/",
        {
            "date": "2026-05-01",
            "description": "Attempt direct posting",
            "status": JournalEntry.Status.POSTED,
            "lines": [
                {"account_code": "1000", "side": "debit", "amount": "100.00"},
                {"account_code": "4000", "side": "credit", "amount": "100.00"},
            ],
        },
        format="json",
    )

    assert response.status_code == 400
    assert "created as drafts" in str(response.data).lower()


@pytest.mark.django_db
def test_journal_entry_status_field_is_rejected_on_patch(api_client, accounting_ready):
    entry_id = create_draft_via_api(api_client)

    response = api_client.patch(
        f"/api/v1/journal-entries/{entry_id}/",
        {"status": JournalEntry.Status.POSTED},
        format="json",
    )

    assert response.status_code == 400
    assert "post or reverse action" in str(response.data).lower()
    assert JournalEntry.objects.get(pk=entry_id).status == JournalEntry.Status.DRAFT


@pytest.mark.django_db
def test_posted_journal_entry_patch_is_rejected(api_client, accounting_ready):
    entry_id = create_draft_via_api(api_client)
    post_response = api_client.post(f"/api/v1/journal-entries/{entry_id}/post/", {}, format="json")
    assert post_response.status_code == 200

    response = api_client.patch(
        f"/api/v1/journal-entries/{entry_id}/",
        {"description": "Should not update posted entry"},
        format="json",
    )

    assert response.status_code == 400
    assert "only draft journal entries" in str(response.data).lower()
    assert JournalEntry.objects.get(pk=entry_id).description == "API cash sale"


@pytest.mark.django_db
def test_journal_entry_put_and_delete_are_disallowed(api_client, accounting_ready):
    entry_id = create_draft_via_api(api_client)

    put_response = api_client.put(
        f"/api/v1/journal-entries/{entry_id}/",
        {"description": "PUT should not be available"},
        format="json",
    )
    delete_response = api_client.delete(f"/api/v1/journal-entries/{entry_id}/")

    assert put_response.status_code == 405
    assert delete_response.status_code == 405
    assert JournalEntry.objects.filter(pk=entry_id).exists()


@pytest.mark.django_db
def test_audit_log_api_is_read_only(api_client, accounting_ready):
    audit_log = AuditLog.objects.latest("id")

    patch_response = api_client.patch(
        f"/api/v1/audit-logs/{audit_log.pk}/",
        {"action": "tampered"},
        format="json",
    )
    delete_response = api_client.delete(f"/api/v1/audit-logs/{audit_log.pk}/")

    assert patch_response.status_code == 405
    assert delete_response.status_code == 405
    audit_log.refresh_from_db()
    assert audit_log.action != "tampered"


@pytest.mark.django_db
def test_period_status_field_is_rejected_on_patch_and_action_changes_status(api_client, accounting_ready):
    period = AccountingPeriod.objects.get(name="FY2026")

    patch_response = api_client.patch(
        f"/api/v1/periods/{period.pk}/",
        {"status": AccountingPeriod.Status.CLOSED},
        format="json",
    )
    action_response = api_client.post(
        f"/api/v1/periods/{period.pk}/change_status/",
        {"status": AccountingPeriod.Status.CLOSED, "reason": "month close"},
        format="json",
    )

    assert patch_response.status_code == 400
    assert "change_status action" in str(patch_response.data).lower()
    assert action_response.status_code == 200
    assert action_response.data["status"] == AccountingPeriod.Status.CLOSED


@pytest.mark.django_db
def test_account_and_period_patch_merge_existing_required_fields(api_client, accounting_ready):
    account = Account.objects.get(account_code="1000")
    period = AccountingPeriod.objects.get(name="FY2026")

    account_response = api_client.patch(
        f"/api/v1/accounts/{account.pk}/",
        {"name": "Operating Cash"},
        format="json",
    )
    period_response = api_client.patch(
        f"/api/v1/periods/{period.pk}/",
        {"name": "Fiscal Year 2026"},
        format="json",
    )

    assert account_response.status_code == 200
    assert account_response.data["name"] == "Operating Cash"
    assert period_response.status_code == 200
    assert period_response.data["name"] == "Fiscal Year 2026"
