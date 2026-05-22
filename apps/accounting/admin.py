from django.contrib import admin

from apps.accounting.models import Account, AccountingPeriod, AuditLog, Entity, JournalEntry, JournalLine


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "slug", "is_default", "is_active"]
    list_filter = ["is_default", "is_active"]


@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ["account_code", "name", "type", "normal_balance", "is_active"]
    list_filter = ["type", "normal_balance", "is_active"]
    search_fields = ["account_code", "name"]


class JournalLineInline(admin.TabularInline):
    model = JournalLine
    extra = 0


@admin.register(JournalEntry)
class JournalEntryAdmin(admin.ModelAdmin):
    list_display = ["id", "date", "description", "status", "source", "period"]
    list_filter = ["status", "source", "date"]
    search_fields = ["description"]
    inlines = [JournalLineInline]


@admin.register(AccountingPeriod)
class AccountingPeriodAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "start_date", "end_date", "status"]
    list_filter = ["status"]


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
