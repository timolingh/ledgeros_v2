from datetime import date

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

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


@pytest.mark.django_db
def test_create_and_post_journal_entry_via_api(api_client, accounting_ready):
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
    entry_id = response.data["id"]
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
