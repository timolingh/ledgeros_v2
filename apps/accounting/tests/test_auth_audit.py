from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model

from apps.accounting.models import AuditLog


def test_failed_django_login_is_audited(db):
    user_model = get_user_model()
    user_model.objects.create_user(username="audit-user", password="correct-password")

    assert authenticate(username="audit-user", password="wrong-password") is None

    audit_log = AuditLog.objects.latest("id")

    assert audit_log.action == "django_login_failed"
    assert audit_log.record_type == "User"
    assert audit_log.record_id == "audit-user"
    assert audit_log.source == "django_auth"
    assert audit_log.metadata == {
        "path": "",
        "reason": "invalid_credentials",
    }
