from __future__ import annotations

# Compatibility import path. Transition rules have one source of truth in
# apps.accounting.transition_rules because models need to import them during
# Django app loading without importing the service package.

from apps.accounting.transition_rules import (  # noqa: F401
    ALLOWED_ACCOUNTING_PERIOD_STATUS_TRANSITIONS,
    ALLOWED_JOURNAL_ENTRY_STATUS_TRANSITIONS,
    validate_accounting_period_status_transition,
    validate_journal_entry_status_transition,
)

__all__ = [
    "ALLOWED_ACCOUNTING_PERIOD_STATUS_TRANSITIONS",
    "ALLOWED_JOURNAL_ENTRY_STATUS_TRANSITIONS",
    "validate_accounting_period_status_transition",
    "validate_journal_entry_status_transition",
]
