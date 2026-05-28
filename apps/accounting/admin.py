from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.models import BaseInlineFormSet
from django.utils import timezone

from apps.accounting.models import Account, AccountingPeriod, AuditLog, JournalEntry, JournalLine
from apps.accounting.services import change_period_status, post_journal_entry, reverse_journal_entry
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.posting import JournalLineInput, assert_line_inputs_balanced, resolve_period_for_posting, update_draft_journal_entry
from apps.accounting.services.writes import save_account, save_accounting_period
from apps.accounting.transition_rules import validate_accounting_period_status_transition, validate_journal_entry_status_transition


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


class JournalEntryAdminForm(forms.ModelForm):
    class Meta:
        model = JournalEntry
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        desired_status = cleaned_data.get("status", self.instance.status)
        if not self.instance.pk:
            if desired_status == JournalEntry.Status.POSTED:
                try:
                    period = cleaned_data.get("period")
                    if period is None:
                        entry_date = cleaned_data.get("date")
                        if entry_date is None:
                            return cleaned_data
                        period = resolve_period_for_posting(get_default_entity(), entry_date)
                    period.assert_posting_allowed()
                except ValidationError as exc:
                    self.add_error("status", exc)
            elif desired_status == JournalEntry.Status.REVERSED:
                self.add_error("status", ValidationError("New journal entries must be created as drafts or posted entries."))
            return cleaned_data

        original_status = JournalEntry.objects.filter(pk=self.instance.pk).values_list("status", flat=True).first()
        try:
            validate_journal_entry_status_transition(original_status=original_status, desired_status=desired_status)
        except ValidationError as exc:
            self.add_error("status", exc)
            return cleaned_data

        if desired_status == original_status:
            return cleaned_data

        if original_status == JournalEntry.Status.DRAFT and desired_status == JournalEntry.Status.POSTED:
            entry_date = cleaned_data.get("date", self.instance.date)
            try:
                period = resolve_period_for_posting(self.instance.entity, entry_date)
                period.assert_posting_allowed()
            except ValidationError as exc:
                self.add_error("status", exc)
        elif original_status == JournalEntry.Status.POSTED and desired_status == JournalEntry.Status.REVERSED:
            reversal_date = timezone.now().date()
            try:
                period = resolve_period_for_posting(self.instance.entity, reversal_date)
                period.assert_posting_allowed()
            except ValidationError as exc:
                self.add_error("status", exc)
        else:
            self.add_error("status", ValidationError("Journal entry status may only be changed through the posting or reversal services."))

        return cleaned_data


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    form = JournalEntryAdminForm
    exclude = ["entity"]
    list_display = ["id", "date", "description", "status", "source", "period"]
    list_filter = ["status", "source", "date"]
    search_fields = ["description"]
    readonly_fields = ["posted_at", "reversed_at", "reversal_of"]
    actions = ["post_selected_entries", "reverse_selected_entries"]
    inlines = [JournalLineInline]
    fieldsets = (
        (None, {"fields": ("date", "description", "status", "source", "period")}),
        ("Status history", {"fields": ("posted_at", "reversed_at", "reversal_of")}),
    )

    def save_model(self, request, obj, form, change):
        if not change and not obj.entity_id:
            obj.entity = get_default_entity()
        if change and obj.pk:
            original_status = JournalEntry.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
            obj.status = original_status
        else:
            obj.status = JournalEntry.Status.DRAFT
        super().save_model(request, obj, form, change)

    @transaction.atomic
    def save_related(self, request, form, formsets, change):
        desired_status = form.cleaned_data.get("status", form.instance.status)
        current_status = JournalEntry.objects.filter(pk=form.instance.pk).values_list("status", flat=True).first()
        reversal_date = timezone.now().date()

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

        if lines and current_status == JournalEntry.Status.DRAFT:
            update_draft_journal_entry(
                entry=form.instance,
                entry_date=form.cleaned_data["date"],
                description=form.cleaned_data["description"],
                lines=lines,
                user=request.user,
                source="admin",
                audit_action="journal_entry_created" if not change else "journal_entry_updated",
            )
        if desired_status == JournalEntry.Status.POSTED and current_status == JournalEntry.Status.DRAFT:
            post_journal_entry(entry=form.instance, user=request.user, source="admin")
        elif desired_status == JournalEntry.Status.REVERSED and current_status == JournalEntry.Status.POSTED:
            reverse_journal_entry(entry=form.instance, reversal_date=reversal_date, user=request.user, source="admin")

    @admin.action(description="Post selected journal entries")
    @transaction.atomic
    def post_selected_entries(self, request, queryset):
        entries = list(queryset.filter(status=JournalEntry.Status.DRAFT))
        for entry in entries:
            post_journal_entry(entry=entry, user=request.user, source="admin")

    @admin.action(description="Reverse selected journal entries")
    @transaction.atomic
    def reverse_selected_entries(self, request, queryset):
        entries = list(queryset.filter(status=JournalEntry.Status.POSTED, reversal_of__isnull=True))
        reversal_date = timezone.now().date()
        for entry in entries:
            reverse_journal_entry(entry=entry, reversal_date=reversal_date, user=request.user, source="admin")


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    class AccountingPeriodAdminForm(forms.ModelForm):
        class Meta:
            model = AccountingPeriod
            fields = "__all__"

        def clean(self):
            cleaned_data = super().clean()
            if self.errors or not self.instance.pk:
                return cleaned_data

            desired_status = cleaned_data.get("status", self.instance.status)
            try:
                validate_accounting_period_status_transition(original_status=self.instance.status, desired_status=desired_status)
            except ValidationError as exc:
                self.add_error("status", exc)
            return cleaned_data

    form = AccountingPeriodAdminForm
    exclude = ["entity"]
    list_display = ["id", "name", "start_date", "end_date", "status"]
    list_filter = ["status"]
    readonly_fields = ["closed_at", "locked_at"]
    actions = ["mark_open", "mark_closed", "mark_locked"]
    fieldsets = (
        (None, {"fields": ("name", "start_date", "end_date", "status")}),
        ("Status history", {"fields": ("closed_at", "locked_at")}),
    )

    def save_model(self, request, obj, form, change):
        desired_status = form.cleaned_data.get("status", obj.status) if form and hasattr(form, "cleaned_data") else obj.status
        original_status = AccountingPeriod.objects.filter(pk=obj.pk).values_list("status", flat=True).first() if change and obj.pk else AccountingPeriod.Status.OPEN
        obj.status = original_status
        save_accounting_period(
            period=obj,
            entity=obj.entity if obj.entity_id else get_default_entity(),
            start_date=obj.start_date,
            end_date=obj.end_date,
            name=obj.name,
        )
        if desired_status != original_status:
            change_period_status(period=obj, status=desired_status, user=request.user, source="admin")

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
