from __future__ import annotations

from apps.accounting.models import AuditLog


def audit_success(*, action: str, record, user=None, source: str = "system", metadata: dict | None = None) -> AuditLog:
    return AuditLog.objects.create(
        action=action,
        record_type=record.__class__.__name__,
        record_id=str(record.pk),
        user=user,
        source=source,
        metadata=metadata or {},
    )
