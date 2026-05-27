from django.contrib import admin
from django.core.exceptions import ValidationError
from django.forms.models import BaseInlineFormSet

from apps.accounting.models import Account, AccountingPeriod, AuditLog, JournalEntry, JournalLine
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
        return obj.posted_balance()

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


class JournalLineInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
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


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["id", "date", "description", "status", "source", "period"]
    list_filter = ["status", "source", "date"]
    search_fields = ["description"]
    readonly_fields = ["status", "posted_at", "reversed_at", "reversal_of"]
    inlines = [JournalLineInline]

    def save_model(self, request, obj, form, change):
        if not change and not obj.entity_id:
            obj.entity = get_default_entity()
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
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

        if lines:
            update_draft_journal_entry(
                entry=form.instance,
                entry_date=form.cleaned_data["date"],
                description=form.cleaned_data["description"],
                lines=lines,
                user=request.user,
                source="admin",
                audit_action="journal_entry_created" if not change else "journal_entry_updated",
            )


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    exclude = ["entity"]
    list_display = ["id", "name", "start_date", "end_date", "status"]
    list_filter = ["status"]
    readonly_fields = ["status", "closed_at", "locked_at"]

    def save_model(self, request, obj, form, change):
        save_accounting_period(
            period=obj,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            start_date=obj.start_date,
            end_date=obj.end_date,
            name=obj.name,
        )


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
