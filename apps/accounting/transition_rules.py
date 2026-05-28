from __future__ import annotations

from collections.abc import Mapping

from django.core.exceptions import ValidationError


ALLOWED_JOURNAL_ENTRY_STATUS_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "draft": frozenset({"draft", "posted"}),
    "posted": frozenset({"posted", "reversed"}),
    "reversed": frozenset({"reversed"}),
}

ALLOWED_ACCOUNTING_PERIOD_STATUS_TRANSITIONS: Mapping[str, frozenset[str]] = {
    "open": frozenset({"open", "closed", "locked"}),
    "closed": frozenset({"closed", "open", "locked"}),
    "locked": frozenset({"locked"}),
}


def validate_journal_entry_status_transition(*, original_status: str, desired_status: str) -> None:
    """Validate the narrow lifecycle used by Epic 1 journal entries.

    Direct callers may keep a status unchanged. Moving from draft to posted and
    posted to reversed is allowed so Django forms can validate objects that the
    service layer is about to save. Business workflows must still call the
    posting and reversal services rather than editing status directly.
    """

    allowed_statuses = ALLOWED_JOURNAL_ENTRY_STATUS_TRANSITIONS.get(
        original_status,
        frozenset({original_status}),
    )
    if desired_status not in allowed_statuses:
        raise ValidationError(
            "Journal entry status may only be changed through the posting or reversal services."
        )


def validate_accounting_period_status_transition(*, original_status: str, desired_status: str) -> None:
    """Validate Epic 1 accounting period transitions.

    Open periods accept postings. Closed and locked periods reject postings.
    Closed periods may be reopened for correction. Locked periods are terminal.
    """

    allowed_statuses = ALLOWED_ACCOUNTING_PERIOD_STATUS_TRANSITIONS.get(
        original_status,
        frozenset({original_status}),
    )
    if desired_status not in allowed_statuses:
        raise ValidationError("Locked accounting periods cannot be reopened or otherwise changed.")
