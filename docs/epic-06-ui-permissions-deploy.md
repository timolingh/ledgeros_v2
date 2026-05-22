# Epic 6 — UI, Permissions, Audit, Import/Export, and Deployment

## Purpose
Build the browser-based Core Accounting UI and supporting infrastructure so users can operate LedgerOS directly and securely.

## In Scope
- Browser-based accounting UI for core workflows
- Permissions and role-based access control
- Audit logs for user and API actions
- CSV import/export support for accounting data
- YAML configuration support for chart of accounts and API clients
- Platform-agnostic deployment tooling
- PostgreSQL production database deployment support

## Why this epic exists
This epic delivers the user-facing and operational capabilities needed to make the accounting module usable without a separate business application.

## Deliverables
- Browser UI for chart of accounts, journals, AR/AP, banking, reconciliation, and reports
- Role and permission model for accounting users
- Audit log surfaces in UI and API
- CSV import for chart of accounts and accounting transactions where appropriate
- CSV export for reports and ledger data
- YAML-based configuration for selected setup objects
- Deployment documentation and tooling for self-hosted use
- Package/launch requirements for platform-agnostic operation

## Implementation Notes
- Implementation must use Django views, templates, and forms with selective HTMX/JavaScript for the Core Accounting UI.
- UI surfaces should be scoped to core accounting operations only, not business workflows.
  - Chart of accounts management
  - Journal entry posting
  - Invoice and bill management
  - Payment and bank transaction recording
  - Bank reconciliation
  - Financial reports and saved views
- Permissions should support at least these roles or capabilities:
  - accounting_admin (manage setup, users, configuration)
  - bookkeeper (create/edit journal entries, invoices, bills)
  - controller (review, close periods, run reports)
  - api_user (API-only access if needed)
- Audit logging should capture:
  - user action, entity, resource, operation, timestamp, and source (UI/API)
  - object changes for journal entries, invoices, payments, reconciliations, and periods
- CSV import/export support should include:
  - import: chart of accounts, optionally journal entry templates or opening balances
  - export: financial reports, ledger journals, customer/vendor lists
- YAML configuration support should be limited to:
  - chart of accounts
  - API client definitions
- Deployment should target platform-agnostic self-hosting and include:
  - PostgreSQL setup guidance
  - application startup scripts or container examples
  - config management guidance for YAML files
  - environment variable standardization for database and API configuration

## Example Success Scenarios
- Create accounts and post journal entries through the browser UI.
- Assign a bookkeeper role to a user and restrict access to reporting-only screens.
- Import a chart-of-accounts YAML file and verify the UI reflects the imported accounts.
- Export a P&L report to CSV and open it with a spreadsheet tool.
- Review an audit log entry showing an API invoice submission and the created record.
- Install and launch the app with PostgreSQL using documented deployment steps.

## Acceptance Criteria
- Users can access the accounting module through a browser UI
- User roles and permissions restrict access to accounting functionality
- Audit logs record UI actions and API event ingestion
- CSV import/export is available for approved MVP data objects
- YAML configuration is supported for chart of accounts and API clients
- Deployment instructions cover PostgreSQL-based production setup and platform-agnostic launch

## Testing Instructions
- Unit tests for:
  - permission checks for UI and API endpoints
  - audit log entry creation for key actions
  - CSV import parsing and validation
  - YAML configuration loading and validation
- Integration tests for:
  - end-to-end UI workflows for account setup, invoice posting, and report generation
  - role-based access restrictions across core screens
  - CSV export contents for reports and ledgers
  - deployment bootstrapping against a PostgreSQL database in a local test environment
- Manual acceptance tests for:
  - browser usability of core accounting flows
  - audit log transparency and filtering
  - deployment instructions runbook completeness

## Dependencies
- Epic 1: Foundational Accounting Core
- Epic 2: AR/AP
- Epic 3: Banking and Reconciliation
- Epic 4: Reporting, Tax, Periods
- Epic 5: API Ingestion and Integration

## Approval
- Status: **Pending**
- Approval required before any code is built against this epic.
