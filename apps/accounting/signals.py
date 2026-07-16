from __future__ import annotations

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

from apps.accounting.models import AuditLog


@receiver(user_login_failed, dispatch_uid="accounting.user_login_failed_audit")
def audit_failed_login(sender, credentials, request, **kwargs) -> None:
    username = ""
    if isinstance(credentials, dict):
        username = str(credentials.get("username") or credentials.get("email") or credentials.get("login") or "").strip()

    path = getattr(request, "path", "") if request is not None else ""
    try:
        AuditLog.objects.create(
            action="django_login_failed",
            record_type="User",
            record_id=username or "unknown",
            source="django_auth",
            metadata={
                "path": path,
                "reason": "invalid_credentials",
            },
        )
    except Exception:
        # Authentication must never fail because auditing failed.
        return
