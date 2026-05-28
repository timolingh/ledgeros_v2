from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounting.models import AccountingPeriod
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.writes import save_accounting_period


def create_accounting_period(*, start_date: date, end_date: date, name: str = "", user=None, source: str = "manual") -> AccountingPeriod:
    entity = get_default_entity()
    period = save_accounting_period(entity=entity, start_date=start_date, end_date=end_date, name=name)
    audit_success(action="period_created", record=period, user=user, source=source, metadata={"status": period.status})
    return period


def change_period_status(*, period: AccountingPeriod, status: str, user=None, source: str = "manual", reason: str = "") -> AccountingPeriod:
    if status not in AccountingPeriod.Status.values:
        raise ValidationError(f"Unsupported accounting period status: {status}")
    before = period.status
    with transaction.atomic():
        if status == AccountingPeriod.Status.CLOSED:
            period.mark_closed()
        elif status == AccountingPeriod.Status.LOCKED:
            period.mark_locked()
        elif status == AccountingPeriod.Status.OPEN:
            period.reopen()
        audit_success(
            action="period_status_changed",
            record=period,
            user=user,
            source=source,
            metadata={"before": before, "after": period.status, "reason": reason},
        )
    return period
