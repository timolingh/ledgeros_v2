from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.utils import timezone

from apps.accounting.models import Account, AccountingPeriod, AuditLog, BankAccount, BankReconciliation, BankReconciliationMatch, BankStatementLine, BankTransaction, JournalEntry, JournalLine, ReportView, SyncEventRecord, TaxCode
from apps.accounting.selectors import account_balance
from apps.accounting.services import change_period_status, post_journal_entry, reverse_journal_entry
from apps.accounting.services.reporting import save_report_view, save_tax_code
from apps.accounting.services.banking import save_bank_account
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.posting import JournalLineInput, assert_line_inputs_balanced, update_draft_journal_entry
from apps.accounting.services.writes import save_account, save_accounting_period


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["account_code", "name", "type", "normal_balance", "posted_balance", "is_active"]
    list_filter = ["type", "normal_balance", "is_active"]
    search_fields = ["account_code", "name"]
    readonly_fields = ["posted_balance"]

    @admin.display(description="Posted balance")
    def posted_balance(self, obj: Account):
        return account_balance(obj)

    def save_model(self, request, obj, form, change):
        save_account(
            account=obj,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            account_code=obj.account_code,
            name=obj.name,
            type=obj.type,
            normal_balance=obj.normal_balance,
            is_active=obj.is_active,
        )


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["name", "bank_name", "account_number", "ledger_account", "status", "current_balance"]
    list_filter = ["status", "bank_name"]
    search_fields = ["name", "account_number", "bank_name"]

    @admin.display(description="Current balance")
    def current_balance(self, obj: BankAccount):
        return obj.current_balance()

    def save_model(self, request, obj, form, change):
        save_bank_account(
            bank_account=obj if change else None,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            name=obj.name,
            account_number=obj.account_number,
            bank_name=obj.bank_name,
            ledger_account=obj.ledger_account,
            status=obj.status,
            user=request.user,
            source="admin",
        )


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ["bank_account", "transaction_date", "transaction_type", "amount", "source_type", "source_id"]
    list_filter = ["transaction_type", "transaction_date", "bank_account"]
    search_fields = ["memo", "source_type"]
    readonly_fields = ["entity", "bank_account", "journal_entry", "transaction_date", "amount", "transaction_type", "source_type", "source_id", "memo", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BankStatementLine)
class BankStatementLineAdmin(admin.ModelAdmin):
    list_display = ["bank_account", "statement_date", "amount", "statement_reference"]
    list_filter = ["statement_date", "bank_account"]
    search_fields = ["description", "statement_reference"]
    readonly_fields = ["entity", "bank_account", "statement_date", "amount", "description", "statement_reference", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BankReconciliation)
class BankReconciliationAdmin(admin.ModelAdmin):
    list_display = ["bank_account", "start_date", "end_date", "status", "statement_ending_balance", "cleared_balance"]
    list_filter = ["status", "bank_account"]
    readonly_fields = ["entity", "bank_account", "start_date", "end_date", "status", "statement_ending_balance", "cleared_balance", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BankReconciliationMatch)
class BankReconciliationMatchAdmin(admin.ModelAdmin):
    list_display = ["reconciliation", "statement_line", "bank_transaction", "matched_amount"]
    readonly_fields = ["reconciliation", "statement_line", "bank_transaction", "matched_amount", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReportView)
class ReportViewAdmin(admin.ModelAdmin):
    exclude = ["entity", "created_by"]
    list_display = ["name", "report_type", "basis", "as_of_date", "start_date", "end_date"]
    list_filter = ["report_type", "basis"]
    search_fields = ["name"]

    def save_model(self, request, obj, form, change):
        obj = save_report_view(
            report_view=obj,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            name=obj.name,
            report_type=obj.report_type,
            basis=obj.basis,
            as_of_date=obj.as_of_date,
            start_date=obj.start_date,
            end_date=obj.end_date,
            filters=obj.filters,
            display_settings=obj.display_settings,
            user=request.user,
            source="admin",
        )


@admin.register(TaxCode)
class TaxCodeAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["code", "name", "jurisdiction", "rate", "liability_account", "is_active"]
    list_filter = ["jurisdiction", "is_active"]
    search_fields = ["code", "name"]

    def save_model(self, request, obj, form, change):
        obj = save_tax_code(
            tax_code=obj,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            code=obj.code,
            name=obj.name,
            rate=obj.rate,
            jurisdiction=obj.jurisdiction,
            liability_account=obj.liability_account,
            is_active=obj.is_active,
            user=request.user,
            source="admin",
        )


@admin.register(SyncEventRecord)
class SyncEventRecordAdmin(admin.ModelAdmin):
    list_display = ["source_system", "domain_event_type", "external_id", "source_object_type", "source_object_id", "status"]
    list_filter = ["source_system", "domain_event_type", "status"]
    search_fields = ["external_id", "source_object_type", "source_object_id"]
    readonly_fields = ["entity", "source_system", "domain_event_type", "external_id", "source_object_type", "source_object_id", "idempotency_key", "request_hash", "occurred_at", "payload", "response_payload", "status", "last_error", "created_at", "updated_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class JournalLineInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        entry = self.instance
        if entry.pk and entry.status != JournalEntry.Status.DRAFT:
            return

        lines = []
        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get("DELETE", False):
                continue
            lines.append(
                JournalLineInput(
                    account_code=form.cleaned_data["account"].account_code,
                    side=form.cleaned_data["side"],
                    amount=form.cleaned_data["amount"],
                    description=form.cleaned_data.get("description", ""),
                )
            )

        if len(lines) < 2:
            raise ValidationError("A journal entry requires at least two lines.")
        assert_line_inputs_balanced(lines)


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0
    formset = JournalLineInlineFormSet
    fields = ["account", "side", "amount", "description"]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.status != JournalEntry.Status.DRAFT:
            return ["account", "side", "amount", "description"]
        return []

    def has_add_permission(self, request, obj=None):
        return obj is None or obj.status == JournalEntry.Status.DRAFT

    def has_change_permission(self, request, obj=None):
        return obj is None or obj.status == JournalEntry.Status.DRAFT

    def has_delete_permission(self, request, obj=None):
        return obj is not None and obj.status == JournalEntry.Status.DRAFT

    def has_view_permission(self, request, obj=None):
        return obj is not None


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["id", "date", "description", "status", "source", "period"]
    list_filter = ["status", "source", "date"]
    search_fields = ["description"]
    actions = ["post_selected_entries", "reverse_selected_entries"]
    inlines = [JournalLineInline]
    fieldsets = (
        (None, {"fields": ("date", "description", "status", "source", "period")}),
        ("Status history", {"fields": ("posted_at", "reversed_at", "reversal_of")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = ["status", "posted_at", "reversed_at", "reversal_of"]
        if obj and obj.status != JournalEntry.Status.DRAFT:
            readonly.extend(["date", "description", "source", "period"])
        return readonly

    def has_delete_permission(self, request, obj=None):
        if obj is None:
            return False
        return obj.status == JournalEntry.Status.DRAFT and super().has_delete_permission(request, obj)

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            original = JournalEntry.objects.get(pk=obj.pk)
            if original.status != JournalEntry.Status.DRAFT:
                return
            obj.status = original.status
            obj.entity = original.entity
        elif not obj.entity_id:
            obj.entity = get_default_entity()
            obj.status = JournalEntry.Status.DRAFT
        super().save_model(request, obj, form, change)

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        entry = form.instance
        if not entry.pk:
            return

        current_status = JournalEntry.objects.filter(pk=entry.pk).values_list("status", flat=True).first()
        if current_status != JournalEntry.Status.DRAFT:
            return

        lines = []
        for formset in formsets:
            if getattr(formset, "model", None) is not JournalLine:
                continue
            formset.save(commit=False)
            for inline_form in formset.forms:
                if not inline_form.cleaned_data or inline_form.cleaned_data.get("DELETE", False):
                    continue
                lines.append(
                    JournalLineInput(
                        account_code=inline_form.cleaned_data["account"].account_code,
                        side=inline_form.cleaned_data["side"],
                        amount=inline_form.cleaned_data["amount"],
                        description=inline_form.cleaned_data.get("description", ""),
                    )
                )

        if not lines:
            return

        update_draft_journal_entry(
            entry=entry,
            entry_date=form.cleaned_data.get("date", entry.date),
            description=form.cleaned_data.get("description", entry.description),
            lines=lines,
            user=request.user,
            source=form.cleaned_data.get("source", entry.source),
            audit_action="journal_entry_created" if not change else "journal_entry_updated",
        )

    @admin.action(description="Post selected draft journal entries")
    @transaction.atomic
    def post_selected_entries(self, request, queryset):
        entries = list(queryset.filter(status=JournalEntry.Status.DRAFT))
        for entry in entries:
            post_journal_entry(entry=entry, user=request.user, source="admin")

    @admin.action(description="Reverse selected posted journal entries")
    @transaction.atomic
    def reverse_selected_entries(self, request, queryset):
        entries = list(queryset.filter(status=JournalEntry.Status.POSTED, reversal_of__isnull=True))
        reversal_date = timezone.now().date()
        for entry in entries:
            reverse_journal_entry(entry=entry, reversal_date=reversal_date, user=request.user, source="admin")


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["id", "name", "start_date", "end_date", "status"]
    list_filter = ["status"]
    actions = ["mark_open", "mark_closed", "mark_locked"]
    fieldsets = (
        (None, {"fields": ("name", "start_date", "end_date", "status")}),
        ("Status history", {"fields": ("closed_at", "locked_at")}),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = ["status", "closed_at", "locked_at"]
        if obj and obj.status == AccountingPeriod.Status.LOCKED:
            readonly.extend(["name", "start_date", "end_date"])
        return readonly

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        if change and obj.pk:
            original = AccountingPeriod.objects.get(pk=obj.pk)
            if original.status == AccountingPeriod.Status.LOCKED:
                return
            obj.status = original.status
            obj.entity = original.entity
        elif not obj.entity_id:
            obj.entity = get_default_entity()
            obj.status = AccountingPeriod.Status.OPEN

        save_accounting_period(
            period=obj,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            start_date=obj.start_date,
            end_date=obj.end_date,
            name=obj.name,
        )

    @admin.action(description="Mark selected periods open")
    def mark_open(self, request, queryset):
        for period in queryset:
            change_period_status(period=period, status=AccountingPeriod.Status.OPEN, user=request.user, source="admin")

    @admin.action(description="Mark selected periods closed")
    def mark_closed(self, request, queryset):
        for period in queryset:
            change_period_status(period=period, status=AccountingPeriod.Status.CLOSED, user=request.user, source="admin")

    @admin.action(description="Mark selected periods locked")
    def mark_locked(self, request, queryset):
        for period in queryset:
            change_period_status(period=period, status=AccountingPeriod.Status.LOCKED, user=request.user, source="admin")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["timestamp", "action", "record_type", "record_id", "source", "user"]
    list_filter = ["action", "record_type", "source"]
    search_fields = ["record_type", "record_id", "action"]
    readonly_fields = ["action", "record_type", "record_id", "user", "source", "timestamp", "metadata"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
