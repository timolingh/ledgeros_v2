from __future__ import annotations

from django.core.exceptions import ValidationError


def validate_journal_entry_status_transition(*, original_status: str, desired_status: str) -> None:
    if desired_status == original_status:
        return

    allowed_statuses = {original_status}
    if original_status == "draft":
        allowed_statuses.add("posted")
    elif original_status == "posted":
        allowed_statuses.add("reversed")

    if desired_status not in allowed_statuses:
        raise ValidationError("Journal entry status may only be changed through the posting or reversal services.")


def validate_accounting_period_status_transition(*, original_status: str, desired_status: str) -> None:
    if desired_status == original_status:
        return

    if original_status == "locked" and desired_status == "soft_closed":
        raise ValidationError("Locked periods cannot be soft-closed.")
