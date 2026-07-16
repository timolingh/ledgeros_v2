# Epic 9 Decision Record

## Purpose
Capture the agreed scope for the next work package so implementation stays aligned with the existing LedgerOS architecture.

## Decisions

1. Single role.
2. Use the existing Django auth and admin flow.
3. Rely on Django for audit history, including failed attempts.
4. Import/export remains docs-only for now.

## Implementation Notes

- No custom role model is required.
- No separate permission-management UI is required.
- Audit history should continue to come from the existing Django-backed audit trail.
- Failed authentication and authorization attempts remain part of the audit story.
- Import/export should be documented, not presented as a dedicated coded workflow.

## Roadmap Items

- Keep the user model and access flow on the built-in Django auth/admin path.
- Preserve audit logging for successful actions and selected failed attempts.
- Document import/export behaviors and explicitly defer a dedicated import/export app or UI.

## Traceability

- Existing Django auth/admin flow: `apps/accounting/admin.py`
- Audit trail model: `apps/accounting/models/audit.py`
- Successful action audit helper: `apps/accounting/services/audit.py`
- Failed API authentication audit events: `apps/accounting/api/authentication.py`

## Deferred

- Custom multi-role permissions model.
- Dedicated import/export screens.
- Any workflow-specific import/export automation beyond the documentation set.
