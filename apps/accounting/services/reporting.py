from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.accounting.models import (
    Account,
    AccountingPeriod,
    BillLine,
    Entity,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    PaymentApplication,
    ReportView,
    TaxCode,
)
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.writes import save_account

MONEY_QUANT = Decimal("0.01")


def money(value: Decimal | str | None) -> Decimal:
    return Decimal(str(value or "0.00")).quantize(MONEY_QUANT)


def _account_payload(account: Account, amount: Decimal) -> dict[str, str]:
    return {
        "account_code": account.account_code,
        "name": account.name,
        "type": account.type,
        "amount": str(money(amount)),
    }


def _bucket_accounts(rows: list[dict[str, str]], account_types: set[str]) -> list[dict[str, str]]:
    return [row for row in rows if row["type"] in account_types]


def _sum_rows(rows: list[dict[str, str]]) -> Decimal:
    return money(sum((Decimal(row["amount"]) for row in rows), Decimal("0.00")))


def _infer_period_status_label(period: AccountingPeriod) -> str:
    return period.status


def _period_payload_for_date(entity: Entity, report_date: date | None) -> dict[str, Any] | None:
    if report_date is None:
        return None
    period = AccountingPeriod.find_for_date(entity=entity, entry_date=report_date)
    if period is None:
        return None
    return {
        "id": period.id,
        "name": period.name,
        "status": period.status,
        "start_date": str(period.start_date),
        "end_date": str(period.end_date),
    }


def _journal_line_detail_payload(line: JournalLine) -> dict[str, Any]:
    return {
        "kind": "journal_line",
        "journal_entry_id": line.journal_entry_id,
        "journal_entry_date": str(line.journal_entry.date),
        "journal_entry_description": line.journal_entry.description,
        "journal_entry_status": line.journal_entry.status,
        "journal_entry_source": line.journal_entry.source,
        "journal_line_id": line.id,
        "account_code": line.account.account_code,
        "account_name": line.account.name,
        "side": line.side,
        "amount": str(money(line.amount)),
        "description": line.description,
    }


def _cash_basis_detail_rows(*, account: Account, entity: Entity, start_date: date, end_date: date) -> list[dict[str, Any]]:
    details: list[dict[str, Any]] = []
    applications = PaymentApplication.objects.select_related("payment", "invoice", "bill").filter(
        payment__entity=entity,
        payment__payment_date__range=(start_date, end_date),
        payment__is_credit_adjustment=False,
    )

    if account.type == Account.AccountType.REVENUE:
        for application in applications.filter(invoice__isnull=False):
            invoice_lines = list(application.invoice.lines.select_related("account").filter(account=account))
            eligible_total = sum(
                (
                    line.amount
                    for line in application.invoice.lines.select_related("account").filter(
                        account__type=Account.AccountType.REVENUE
                    )
                ),
                Decimal("0.00"),
            )
            if eligible_total <= Decimal("0.00"):
                continue
            for line in invoice_lines:
                allocated_amount = money(application.applied_amount * line.amount / eligible_total)
                details.append(
                    {
                        "kind": "payment_application",
                        "source_type": "invoice",
                        "payment_id": application.payment_id,
                        "payment_date": str(application.payment.payment_date),
                        "application_id": application.id,
                        "invoice_id": application.invoice_id,
                        "invoice_number": application.invoice.invoice_number,
                        "line_id": line.id,
                        "line_description": line.line_description,
                        "account_code": line.account.account_code,
                        "account_name": line.account.name,
                        "applied_amount": str(money(application.applied_amount)),
                        "allocated_amount": str(allocated_amount),
                    }
                )

    if account.type == Account.AccountType.EXPENSE:
        for application in applications.filter(bill__isnull=False):
            bill_lines = list(application.bill.lines.select_related("account").filter(account=account))
            eligible_total = sum(
                (
                    line.amount
                    for line in application.bill.lines.select_related("account").filter(
                        account__type=Account.AccountType.EXPENSE
                    )
                ),
                Decimal("0.00"),
            )
            if eligible_total <= Decimal("0.00"):
                continue
            for line in bill_lines:
                allocated_amount = money(application.applied_amount * line.amount / eligible_total)
                details.append(
                    {
                        "kind": "payment_application",
                        "source_type": "bill",
                        "payment_id": application.payment_id,
                        "payment_date": str(application.payment.payment_date),
                        "application_id": application.id,
                        "bill_id": application.bill_id,
                        "bill_number": application.bill.bill_number,
                        "line_id": line.id,
                        "line_description": line.line_description,
                        "account_code": line.account.account_code,
                        "account_name": line.account.name,
                        "applied_amount": str(money(application.applied_amount)),
                        "allocated_amount": str(allocated_amount),
                    }
                )

    return sorted(
        details,
        key=lambda row: (
            row["payment_date"],
            row["payment_id"],
            row["application_id"],
            row["kind"],
            row["line_id"],
        ),
    )


def _journal_line_detail_rows(*, account: Account, entity: Entity, start_date: date | None = None, end_date: date | None = None) -> list[dict[str, Any]]:
    queryset = JournalLine.objects.select_related("account", "journal_entry").filter(
        account=account,
        journal_entry__entity=entity,
        journal_entry__status__in=JournalEntry.ledger_affecting_statuses(),
    )
    if start_date is not None:
        queryset = queryset.filter(journal_entry__date__gte=start_date)
    if end_date is not None:
        queryset = queryset.filter(journal_entry__date__lte=end_date)
    return [_journal_line_detail_payload(line) for line in queryset.order_by("journal_entry__date", "journal_entry__id", "id")]


def _cash_basis_pl_from_payments(entity: Entity, start_date: date, end_date: date) -> dict[str, Any]:
    revenue_totals: dict[str, dict[str, str]] = {}
    expense_totals: dict[str, dict[str, str]] = {}

    applications = PaymentApplication.objects.select_related(
        "payment",
        "invoice",
        "bill",
    ).filter(
        payment__entity=entity,
        payment__payment_date__range=(start_date, end_date),
        payment__is_credit_adjustment=False,
    )

    for application in applications:
        if application.invoice_id:
            lines = list(
                application.invoice.lines.select_related("account").filter(account__type=Account.AccountType.REVENUE)
            )
            eligible_total = sum((line.amount for line in lines), Decimal("0.00"))
            if eligible_total <= Decimal("0.00"):
                continue
            for line in lines:
                amount = money(application.applied_amount * line.amount / eligible_total)
                bucket = revenue_totals.setdefault(
                    line.account.account_code,
                    _account_payload(line.account, Decimal("0.00")),
                )
                bucket["amount"] = str(money(Decimal(bucket["amount"]) + amount))
        elif application.bill_id:
            lines = list(
                application.bill.lines.select_related("account").filter(account__type=Account.AccountType.EXPENSE)
            )
            eligible_total = sum((line.amount for line in lines), Decimal("0.00"))
            if eligible_total <= Decimal("0.00"):
                continue
            for line in lines:
                amount = money(application.applied_amount * line.amount / eligible_total)
                bucket = expense_totals.setdefault(
                    line.account.account_code,
                    _account_payload(line.account, Decimal("0.00")),
                )
                bucket["amount"] = str(money(Decimal(bucket["amount"]) + amount))

    revenue_rows = sorted(revenue_totals.values(), key=lambda row: row["account_code"])
    expense_rows = sorted(expense_totals.values(), key=lambda row: row["account_code"])
    revenue_total = _sum_rows(revenue_rows)
    expense_total = _sum_rows(expense_rows)
    return {
        "basis": ReportView.Basis.CASH,
        "report_type": ReportView.ReportType.PROFIT_AND_LOSS,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "sections": [
            {"group": "revenue", "accounts": revenue_rows, "total": str(revenue_total)},
            {"group": "expense", "accounts": expense_rows, "total": str(expense_total)},
        ],
        "totals": {
            "revenue": str(revenue_total),
            "expense": str(expense_total),
            "net_income": str(money(revenue_total - expense_total)),
        },
    }


def _accrual_pl(entity: Entity, start_date: date, end_date: date) -> dict[str, Any]:
    rows: dict[str, dict[str, str]] = {}
    journal_lines = JournalLine.objects.select_related("account", "journal_entry").filter(
        journal_entry__entity=entity,
        journal_entry__status__in=JournalEntry.ledger_affecting_statuses(),
        journal_entry__date__range=(start_date, end_date),
        account__type__in=[Account.AccountType.REVENUE, Account.AccountType.EXPENSE],
    )
    for line in journal_lines:
        amount = line.amount if line.account.type == Account.AccountType.EXPENSE else line.amount
        bucket = rows.setdefault(line.account.account_code, _account_payload(line.account, Decimal("0.00")))
        bucket["amount"] = str(money(Decimal(bucket["amount"]) + amount))

    revenue_rows = sorted([row for row in rows.values() if row["type"] == Account.AccountType.REVENUE], key=lambda row: row["account_code"])
    expense_rows = sorted([row for row in rows.values() if row["type"] == Account.AccountType.EXPENSE], key=lambda row: row["account_code"])
    revenue_total = _sum_rows(revenue_rows)
    expense_total = _sum_rows(expense_rows)
    return {
        "basis": ReportView.Basis.ACCRUAL,
        "report_type": ReportView.ReportType.PROFIT_AND_LOSS,
        "start_date": str(start_date),
        "end_date": str(end_date),
        "sections": [
            {"group": "revenue", "accounts": revenue_rows, "total": str(revenue_total)},
            {"group": "expense", "accounts": expense_rows, "total": str(expense_total)},
        ],
        "totals": {
            "revenue": str(revenue_total),
            "expense": str(expense_total),
            "net_income": str(money(revenue_total - expense_total)),
        },
    }


def generate_profit_and_loss(*, entity: Entity | None = None, start_date: date, end_date: date, basis: str = ReportView.Basis.ACCRUAL) -> dict[str, Any]:
    entity = entity or get_default_entity()
    if basis == ReportView.Basis.CASH:
        report = _cash_basis_pl_from_payments(entity=entity, start_date=start_date, end_date=end_date)
        report["period"] = _period_payload_for_date(entity, end_date)
        return report
    if basis != ReportView.Basis.ACCRUAL:
        raise ValidationError(f"Unsupported report basis: {basis}")
    report = _accrual_pl(entity=entity, start_date=start_date, end_date=end_date)
    report["period"] = _period_payload_for_date(entity, end_date)
    return report


def generate_balance_sheet(*, entity: Entity | None = None, as_of: date, basis: str = ReportView.Basis.ACCRUAL) -> dict[str, Any]:
    entity = entity or get_default_entity()
    if basis != ReportView.Basis.ACCRUAL:
        raise ValidationError("Balance sheet supports accrual basis only in Epic 4.")

    from apps.accounting.selectors.reporting import trial_balance_as_of

    trial = trial_balance_as_of(entity=entity, as_of=as_of)
    revenue_total = _sum_rows([{"amount": row["balance"]} for row in trial if row["type"] == Account.AccountType.REVENUE])
    expense_total = _sum_rows([{"amount": row["balance"]} for row in trial if row["type"] == Account.AccountType.EXPENSE])
    net_income = money(revenue_total - expense_total)
    rows_by_type = {
        "assets": [row for row in trial if row["type"] == Account.AccountType.ASSET],
        "liabilities": [row for row in trial if row["type"] == Account.AccountType.LIABILITY],
        "equity": [row for row in trial if row["type"] == Account.AccountType.EQUITY],
    }
    sections = []
    totals: dict[str, str] = {}
    for group_name, rows in rows_by_type.items():
        total = _sum_rows([{"amount": row["balance"]} for row in rows])
        sections.append({"group": group_name, "accounts": rows, "total": str(total)})
        totals[group_name] = str(total)

    if net_income != Decimal("0.00"):
        current_earnings = {
            "account_code": "current_earnings",
            "name": "Current period earnings",
            "type": Account.AccountType.EQUITY,
            "normal_balance": Account.NormalBalance.CREDIT,
            "debits": str(Decimal("0.00")),
            "credits": str(Decimal("0.00")),
            "balance": str(net_income),
            "synthetic": True,
        }
        sections[2]["accounts"].append(current_earnings)
        totals["equity"] = str(money(Decimal(totals["equity"]) + net_income))
        sections[2]["total"] = totals["equity"]

    liabilities_plus_equity = money(Decimal(totals["liabilities"]) + Decimal(totals["equity"]))
    totals["liabilities_plus_equity"] = str(liabilities_plus_equity)
    totals["difference"] = str(money(Decimal(totals["assets"]) - liabilities_plus_equity))
    totals["net_income"] = str(net_income)

    return {
        "basis": ReportView.Basis.ACCRUAL,
        "report_type": ReportView.ReportType.BALANCE_SHEET,
        "as_of": str(as_of),
        "sections": sections,
        "totals": totals,
        "period": _period_payload_for_date(entity, as_of),
    }


def generate_report_drilldown(
    *,
    entity: Entity | None = None,
    report_type: str,
    account_code: str,
    basis: str = ReportView.Basis.ACCRUAL,
    as_of: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
) -> dict[str, Any]:
    entity = entity or get_default_entity()
    account = Account.objects.get(entity=entity, account_code=account_code, is_active=True)

    if report_type == ReportView.ReportType.BALANCE_SHEET:
        if as_of is None:
            raise ValidationError({"as_of": "This query parameter is required."})
        if basis != ReportView.Basis.ACCRUAL:
            raise ValidationError("Balance sheet drill-down supports accrual basis only in Epic 4.")
        rows = _journal_line_detail_rows(account=account, entity=entity, end_date=as_of)
        return {
            "report_type": report_type,
            "basis": basis,
            "account_code": account.account_code,
            "account_name": account.name,
            "period": _period_payload_for_date(entity, as_of),
            "rows": rows,
            "total_amount": str(_sum_rows([{"amount": row["amount"]} for row in rows])),
        }

    if report_type == ReportView.ReportType.PROFIT_AND_LOSS:
        if start_date is None or end_date is None:
            raise ValidationError("Profit and loss drill-down requires both start_date and end_date.")
        if basis == ReportView.Basis.CASH:
            rows = _cash_basis_detail_rows(account=account, entity=entity, start_date=start_date, end_date=end_date)
        elif basis == ReportView.Basis.ACCRUAL:
            rows = _journal_line_detail_rows(account=account, entity=entity, start_date=start_date, end_date=end_date)
        else:
            raise ValidationError(f"Unsupported report basis: {basis}")
        return {
            "report_type": report_type,
            "basis": basis,
            "account_code": account.account_code,
            "account_name": account.name,
            "period": _period_payload_for_date(entity, end_date),
            "rows": rows,
            "total_amount": str(_sum_rows([{"amount": row["amount"] if row["kind"] == "journal_line" else row["allocated_amount"]} for row in rows])),
        }

    raise ValidationError({"report_type": "Unsupported report type."})


def summarize_period(*, period: AccountingPeriod) -> dict[str, Any]:
    from apps.accounting.selectors.reporting import trial_balance_as_of

    journal_entries = JournalEntry.objects.filter(
        entity=period.entity,
        date__range=(period.start_date, period.end_date),
        status__in=JournalEntry.ledger_affecting_statuses(),
    )
    trial = trial_balance_as_of(entity=period.entity, as_of=period.end_date)
    debits = Decimal("0.00")
    credits = Decimal("0.00")
    for row in trial:
        debits += Decimal(row["debits"])
        credits += Decimal(row["credits"])
    return {
        "period_id": period.id,
        "name": period.name,
        "status": _infer_period_status_label(period),
        "start_date": str(period.start_date),
        "end_date": str(period.end_date),
        "journal_entry_count": journal_entries.count(),
        "posted_debits": str(money(debits)),
        "posted_credits": str(money(credits)),
        "balance_check": str(money(debits - credits)),
    }


def tax_summary(*, entity: Entity | None = None) -> dict[str, Any]:
    entity = entity or get_default_entity()
    from apps.accounting.selectors.reporting import account_balance_as_of

    rows = []
    for tax_code in TaxCode.objects.filter(entity=entity, is_active=True).select_related("liability_account").order_by("code"):
        rows.append(
            {
                "code": tax_code.code,
                "name": tax_code.name,
                "jurisdiction": tax_code.jurisdiction,
                "rate": str(tax_code.rate),
                "liability_account_code": tax_code.liability_account.account_code,
                "liability_account_name": tax_code.liability_account.name,
                "liability_balance": str(account_balance_as_of(tax_code.liability_account)),
            }
        )
    return {"entity_id": entity.id, "tax_codes": rows}


@transaction.atomic
def save_report_view(
    *,
    report_view: ReportView | None = None,
    entity: Entity | None = None,
    name: str,
    report_type: str,
    basis: str = ReportView.Basis.ACCRUAL,
    as_of_date: date | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    filters: dict[str, Any] | None = None,
    display_settings: dict[str, Any] | None = None,
    user=None,
    source: str = "manual",
) -> ReportView:
    entity = entity or get_default_entity()
    if report_view is None:
        report_view = ReportView(
            entity=entity,
            name=name,
            report_type=report_type,
            basis=basis,
            as_of_date=as_of_date,
            start_date=start_date,
            end_date=end_date,
            filters=filters or {},
            display_settings=display_settings or {},
            created_by=user,
        )
    else:
        report_view.name = name
        report_view.report_type = report_type
        report_view.basis = basis
        report_view.as_of_date = as_of_date
        report_view.start_date = start_date
        report_view.end_date = end_date
        report_view.filters = filters or {}
        report_view.display_settings = display_settings or {}
        if not report_view.entity_id:
            report_view.entity = entity
    report_view.full_clean()
    report_view.save()
    audit_success(action="report_view_saved", record=report_view, user=user, source=source)
    return report_view


@transaction.atomic
def save_tax_code(
    *,
    tax_code: TaxCode | None = None,
    entity: Entity | None = None,
    code: str,
    name: str,
    rate: Decimal,
    jurisdiction: str,
    liability_account: Account,
    is_active: bool = True,
    user=None,
    source: str = "manual",
) -> TaxCode:
    entity = entity or get_default_entity()
    if tax_code is None:
        tax_code = TaxCode(
            entity=entity,
            code=code,
            name=name,
            rate=rate,
            jurisdiction=jurisdiction,
            liability_account=liability_account,
            is_active=is_active,
        )
    else:
        tax_code.code = code
        tax_code.name = name
        tax_code.rate = rate
        tax_code.jurisdiction = jurisdiction
        tax_code.liability_account = liability_account
        tax_code.is_active = is_active
        if not tax_code.entity_id:
            tax_code.entity = entity
    tax_code.full_clean()
    tax_code.save()
    audit_success(action="tax_code_saved", record=tax_code, user=user, source=source)
    return tax_code


def run_report_view(*, report_view: ReportView) -> dict[str, Any]:
    if report_view.report_type == ReportView.ReportType.BALANCE_SHEET:
        return generate_balance_sheet(entity=report_view.entity, as_of=report_view.as_of_date, basis=report_view.basis)
    if report_view.report_type == ReportView.ReportType.PROFIT_AND_LOSS:
        return generate_profit_and_loss(
            entity=report_view.entity,
            start_date=report_view.start_date,
            end_date=report_view.end_date,
            basis=report_view.basis,
        )
    raise ValidationError({"report_type": "Unsupported report type."})
