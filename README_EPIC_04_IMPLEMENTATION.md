# LedgerOS Epic 4 Reporting, Periods, and Tax Support Implementation

This document describes the Epic 4 implementation for LedgerOS, building on the foundational accounting core from Epic 1 plus the AR/AP and banking flows from Epics 2 and 3.

## Scope Implemented

- Balance sheet reporting on accrual basis
- Profit and loss reporting on cash and accrual bases
- Saved report views with persistence and retrieval through the API
- Report drill-down into supporting journal entries and payment applications
- Report API endpoints for standard reports, saved views, drill-down, and tax summary
- Period summary reporting with status visibility
- Tax code configuration with US and California jurisdiction support
- Tax summary reporting that surfaces tax liability accounts and balances
- Docker-ready validation commands and manual acceptance checks

## Explicit Domain Assumptions

- MVP uses the hidden default entity for report, period, and tax access.
- Standard reports are generated from posted ledger activity, not mutable UI state.
- Balance sheet reporting includes a computed current-earnings bridge so assets equal liabilities plus equity in an in-period report.
- Cash-basis P&L is derived from payment activity and payment applications.
- Accrual-basis P&L is derived from posted journal lines.
- Drill-down for accrual reports exposes posted journal lines.
- Drill-down for cash reports exposes payment applications and their proportional allocation to invoice or bill lines.
- Period summaries reflect the accounting period status and ledger balance check.
- Tax support in Epic 4 covers tax code mapping and tax liability reporting, not a full tax engine for invoice-line tax calculation.

## Requirement Traceability Matrix

| Requirement | Source | Status | Code location | Test / manual check |
|---|---|---|---|---|
| Generate balance sheet | Epic 4 / PRD REPORT-002 | Implemented | `apps/accounting/services/reporting.py` | `apps/accounting/tests/test_reporting_service.py` |
| Generate profit and loss | Epic 4 / PRD REPORT-003 | Implemented | `apps/accounting/services/reporting.py` | `apps/accounting/tests/test_reporting_service.py` |
| Cash-basis P&L | Epic 4 / PRD BASIS-003, BASIS-007 | Implemented | `apps/accounting/services/reporting.py` | `apps/accounting/tests/test_reporting_service.py` |
| Accrual-basis P&L | Epic 4 / PRD BASIS-003, BASIS-008 | Implemented | `apps/accounting/services/reporting.py` | `apps/accounting/tests/test_reporting_service.py` |
| Saved report views persist and reload | Epic 4 / PRD REPORT-011, REPORT-012 | Implemented | `apps/accounting/models/reporting.py`, `apps/accounting/services/reporting.py`, `apps/accounting/api/views.py` | `apps/accounting/tests/test_reporting_service.py`, `apps/accounting/tests/test_reporting_api.py` |
| Report drill-down | Epic 4 / PRD REPORT-010 | Implemented | `apps/accounting/services/reporting.py`, `apps/accounting/api/views.py` | `apps/accounting/tests/test_reporting_service.py`, `apps/accounting/tests/test_reporting_api.py` |
| Report APIs | Epic 4 / PRD REPORT-017 | Implemented | `apps/accounting/api/views.py`, `apps/accounting/api/urls.py` | `apps/accounting/tests/test_reporting_api.py` |
| Period summary and status visibility | Epic 4 / PRD PERIOD-001 to PERIOD-005 | Implemented | `apps/accounting/services/reporting.py`, `apps/accounting/api/views.py` | `apps/accounting/tests/test_reporting_service.py`, `apps/accounting/tests/test_reporting_api.py` |
| Tax code mapping | Epic 4 / PRD TAX-001, TAX-005 | Implemented | `apps/accounting/models/reporting.py`, `apps/accounting/services/reporting.py` | `apps/accounting/tests/test_reporting_service.py` |
| Tax summary reporting | Epic 4 / PRD TAX-003 | Implemented | `apps/accounting/services/reporting.py`, `apps/accounting/api/views.py` | `apps/accounting/tests/test_reporting_service.py`, `apps/accounting/tests/test_reporting_api.py` |
| Dockerized runtime checks | Epic 4 / Epic guardrails | Implemented | `scripts/check.sh`, project Docker config | Manual commands below |
| Trial balance API/report | PRD REPORT-001 | Deferred | N/A | Covered by Epic 1 selectors, not exposed as an Epic 4 API surface |
| General ledger report | PRD REPORT-004 | Deferred | N/A | Planned for a later reporting epic |
| AR aging / AP aging | PRD REPORT-005 / REPORT-006 | Deferred | N/A | Provided by subledger epics, not Epic 4 |
| CSV export | PRD REPORT-007 / REPORT-013 / TAX-006 | Deferred | N/A | Future reporting/export work |
| Full tax calculation on invoice lines | PRD TAX-002 / TAX-004 | Deferred | N/A | Epic 4 currently provides tax code mapping and tax summary only |

## Structure

```text
apps/accounting/
  models/
    reporting.py              # ReportView and TaxCode models
  services/
    reporting.py              # Standard report generation, drill-down, tax summary, saved views
  api/
    views.py                  # Report endpoints and drill-down endpoint
  tests/
    test_reporting_service.py  # Report and tax service tests
    test_reporting_api.py      # Report API tests
```

## Local Run

Starting from a running Docker environment:

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py makemigrations --check --dry-run
docker compose run --rm web pytest apps/accounting/tests/test_reporting_service.py -v
docker compose run --rm web pytest apps/accounting/tests/test_reporting_api.py -v
```

## Manual Acceptance Checks

Generate a balance sheet:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import generate_balance_sheet

report = generate_balance_sheet(as_of=date(2026, 5, 31))
print(report["totals"])
PY
```

Generate a cash-basis profit and loss report:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import generate_profit_and_loss

report = generate_profit_and_loss(start_date=date(2026, 5, 1), end_date=date(2026, 5, 31), basis="cash")
print(report["totals"])
PY
```

Save and rerun a report view:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import save_report_view, run_report_view

view = save_report_view(
    name="May Cash P&L",
    report_type="profit_and_loss",
    basis="cash",
    start_date=date(2026, 5, 1),
    end_date=date(2026, 5, 31),
)
print(run_report_view(report_view=view)["totals"])
PY
```

Drill into a saved report view:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from datetime import date
from apps.accounting.services import generate_report_drilldown

detail = generate_report_drilldown(
    report_type="profit_and_loss",
    account_code="4000",
    basis="cash",
    start_date=date(2026, 5, 1),
    end_date=date(2026, 5, 31),
)
print(detail["rows"])
PY
```

Check tax summary output:

```bash
docker compose run --rm -T web python manage.py shell <<'PY'
from apps.accounting.services import tax_summary

print(tax_summary())
PY
```

## Notes

- Epic 4 is implemented to the approved reporting/period/tax scope in the epic document.
- Items that belong to later reporting scope are documented as deferred rather than being silently scaffolded.
