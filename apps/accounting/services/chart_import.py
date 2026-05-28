from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounting.models import Account, Entity
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.writes import save_account


@dataclass(frozen=True)
class COAImportResult:
    created: int
    updated: int
    unchanged: int


def load_chart_of_accounts_yaml(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValidationError("Chart of accounts YAML must be a mapping.")
    return data


def validate_chart_of_accounts_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        raise ValidationError("Chart of accounts YAML must contain a non-empty accounts list.")
    validated: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for index, item in enumerate(accounts, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"Account entry {index} must be a mapping.")
        code = str(item.get("code", "")).strip()
        name = str(item.get("name", "")).strip()
        account_type = str(item.get("type", "")).strip()
        normal_balance = str(item.get("normal_balance", "")).strip()
        is_active = bool(item.get("is_active", True))
        if not code or not name or not account_type or not normal_balance:
            raise ValidationError(f"Account entry {index} requires code, name, type, and normal_balance.")
        if code in seen_codes:
            raise ValidationError(f"Duplicate account code in YAML: {code}")
        if account_type not in Account.AccountType.values:
            raise ValidationError(f"Invalid account type for {code}: {account_type}")
        if normal_balance not in Account.NormalBalance.values:
            raise ValidationError(f"Invalid normal balance for {code}: {normal_balance}")
        expected = Account.expected_normal_balance(account_type)
        if normal_balance != expected:
            raise ValidationError(f"Account {code} has normal_balance {normal_balance}; expected {expected} for {account_type}.")
        seen_codes.add(code)
        validated.append(
            {
                "account_code": code,
                "name": name,
                "type": account_type,
                "normal_balance": normal_balance,
                "is_active": is_active,
            }
        )
    return validated


@transaction.atomic
def import_chart_of_accounts(*, path: str | Path, entity: Entity | None = None, user=None, source: str = "management_command") -> COAImportResult:
    entity = entity or get_default_entity()
    accounts = validate_chart_of_accounts_payload(load_chart_of_accounts_yaml(path))
    created = updated = unchanged = 0
    for item in accounts:
        account = Account.objects.filter(entity=entity, account_code=item["account_code"]).first()
        if account is None:
            save_account(entity=entity, **item)
            created += 1
            continue
        if any(getattr(account, field) != item[field] for field in ["name", "type", "normal_balance", "is_active"]):
            save_account(account=account, entity=entity, **item)
            updated += 1
        else:
            unchanged += 1
    result = COAImportResult(created=created, updated=updated, unchanged=unchanged)
    audit_success(
        action="chart_of_accounts_imported",
        record=entity,
        user=user,
        source=source,
        metadata={"created": created, "updated": updated, "unchanged": unchanged},
    )
    return result
