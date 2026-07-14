from __future__ import annotations

from datetime import date

from rest_framework import serializers

from apps.accounting.models import (
    Account,
    AccountingPeriod,
    AuditLog,
    BankAccount,
    BankReconciliation,
    Entity,
    JournalEntry,
    JournalLine,
    ReportView,
    TaxCode,
)
from apps.accounting.selectors import account_balance
from apps.accounting.selectors.banking import bank_account_balance
from apps.accounting.services import JournalLineInput, post_journal_entry, reverse_journal_entry, update_draft_journal_entry
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.reporting import save_report_view, save_tax_code
from apps.accounting.services.posting import create_draft_journal_entry
from apps.accounting.services.writes import save_account, save_accounting_period


class EntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ["id", "name", "slug", "is_default", "is_active", "created_at"]
        read_only_fields = fields


class AccountSerializer(serializers.ModelSerializer):
    posted_balance = serializers.SerializerMethodField()

    class Meta:
        model = Account
        fields = ["id", "account_code", "name", "type", "normal_balance", "is_active", "posted_balance", "created_at", "updated_at"]
        read_only_fields = ["id", "posted_balance", "created_at", "updated_at"]

    def get_posted_balance(self, obj: Account) -> str:
        return str(account_balance(obj))

    def create(self, validated_data):
        return save_account(entity=get_default_entity(), **validated_data)

    def update(self, instance: Account, validated_data):
        return save_account(
            account=instance,
            entity=instance.entity,
            account_code=validated_data.get("account_code", instance.account_code),
            name=validated_data.get("name", instance.name),
            type=validated_data.get("type", instance.type),
            normal_balance=validated_data.get("normal_balance", instance.normal_balance),
            is_active=validated_data.get("is_active", instance.is_active),
        )


class AccountingPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountingPeriod
        fields = ["id", "name", "start_date", "end_date", "status", "closed_at", "locked_at", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "closed_at", "locked_at", "created_at", "updated_at"]

    def update(self, instance: AccountingPeriod, validated_data):
        return save_accounting_period(
            period=instance,
            entity=instance.entity,
            start_date=validated_data.get("start_date", instance.start_date),
            end_date=validated_data.get("end_date", instance.end_date),
            name=validated_data.get("name", instance.name),
        )


class ReportViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReportView
        fields = [
            "id",
            "name",
            "report_type",
            "basis",
            "as_of_date",
            "start_date",
            "end_date",
            "filters",
            "display_settings",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return save_report_view(entity=get_default_entity(), user=user if getattr(user, "is_authenticated", False) else None, **validated_data)

    def update(self, instance: ReportView, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return save_report_view(
            report_view=instance,
            entity=instance.entity,
            user=user if getattr(user, "is_authenticated", False) else None,
            name=validated_data.get("name", instance.name),
            report_type=validated_data.get("report_type", instance.report_type),
            basis=validated_data.get("basis", instance.basis),
            as_of_date=validated_data.get("as_of_date", instance.as_of_date),
            start_date=validated_data.get("start_date", instance.start_date),
            end_date=validated_data.get("end_date", instance.end_date),
            filters=validated_data.get("filters", instance.filters),
            display_settings=validated_data.get("display_settings", instance.display_settings),
        )


class TaxCodeSerializer(serializers.ModelSerializer):
    liability_account_code = serializers.CharField(source="liability_account.account_code", read_only=True)
    liability_account_name = serializers.CharField(source="liability_account.name", read_only=True)

    class Meta:
        model = TaxCode
        fields = [
            "id",
            "code",
            "name",
            "rate",
            "jurisdiction",
            "liability_account",
            "liability_account_code",
            "liability_account_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "liability_account_code", "liability_account_name", "created_at", "updated_at"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return save_tax_code(entity=get_default_entity(), user=user if getattr(user, "is_authenticated", False) else None, **validated_data)

    def update(self, instance: TaxCode, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return save_tax_code(
            tax_code=instance,
            entity=instance.entity,
            user=user if getattr(user, "is_authenticated", False) else None,
            code=validated_data.get("code", instance.code),
            name=validated_data.get("name", instance.name),
            rate=validated_data.get("rate", instance.rate),
            jurisdiction=validated_data.get("jurisdiction", instance.jurisdiction),
            liability_account=validated_data.get("liability_account", instance.liability_account),
            is_active=validated_data.get("is_active", instance.is_active),
        )


class BankAccountSerializer(serializers.ModelSerializer):
    current_balance = serializers.SerializerMethodField()
    ledger_account_code = serializers.CharField(source="ledger_account.account_code", read_only=True)
    ledger_account_name = serializers.CharField(source="ledger_account.name", read_only=True)

    class Meta:
        model = BankAccount
        fields = [
            "id",
            "name",
            "bank_name",
            "account_number",
            "status",
            "ledger_account",
            "ledger_account_code",
            "ledger_account_name",
            "current_balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_current_balance(self, obj: BankAccount) -> str:
        return str(bank_account_balance(obj))


class BankReconciliationSerializer(serializers.ModelSerializer):
    bank_account_name = serializers.CharField(source="bank_account.name", read_only=True)
    bank_account_ledger_account_code = serializers.CharField(source="bank_account.ledger_account.account_code", read_only=True)
    bank_account_ledger_account_name = serializers.CharField(source="bank_account.ledger_account.name", read_only=True)
    book_balance = serializers.SerializerMethodField()

    class Meta:
        model = BankReconciliation
        fields = [
            "id",
            "bank_account",
            "bank_account_name",
            "bank_account_ledger_account_code",
            "bank_account_ledger_account_name",
            "start_date",
            "end_date",
            "status",
            "statement_ending_balance",
            "cleared_balance",
            "book_balance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_book_balance(self, obj: BankReconciliation) -> str:
        return str(bank_account_balance(obj.bank_account, as_of=obj.end_date))


class BankTransactionSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    bank_account = serializers.IntegerField(read_only=True)
    bank_account_name = serializers.CharField(read_only=True)
    transaction_date = serializers.DateField(read_only=True)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    transaction_type = serializers.CharField(read_only=True)
    source_type = serializers.CharField(read_only=True)
    source_id = serializers.IntegerField(read_only=True, allow_null=True)
    memo = serializers.CharField(read_only=True)
    journal_entry_id = serializers.IntegerField(read_only=True, allow_null=True)
    journal_entry_status = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source="account.account_code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)

    class Meta:
        model = JournalLine
        fields = ["id", "account", "account_code", "account_name", "side", "amount", "description"]
        read_only_fields = fields


class JournalLineInputSerializer(serializers.Serializer):
    account_code = serializers.CharField(max_length=32)
    side = serializers.ChoiceField(choices=JournalLine.Side.choices)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def to_line_input(self) -> JournalLineInput:
        data = self.validated_data
        return JournalLineInput(
            account_code=data["account_code"],
            side=data["side"],
            amount=data["amount"],
            description=data.get("description", ""),
        )


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)
    total_debits = serializers.SerializerMethodField()
    total_credits = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            "id",
            "date",
            "description",
            "status",
            "source",
            "period",
            "posted_at",
            "reversed_at",
            "reversal_of",
            "lines",
            "total_debits",
            "total_credits",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_total_debits(self, obj: JournalEntry) -> str:
        return str(obj.total_debits)

    def get_total_credits(self, obj: JournalEntry) -> str:
        return str(obj.total_credits)


class JournalEntryWriteSerializer(serializers.Serializer):
    date = serializers.DateField(required=False)
    description = serializers.CharField(required=False)
    source = serializers.CharField(required=False, default="manual")
    lines = JournalLineInputSerializer(many=True, required=False)

    def validate(self, attrs):
        if self.instance is None:
            missing = [field for field in ("date", "description", "lines") if field not in attrs]
            if missing:
                raise serializers.ValidationError({field: "This field is required." for field in missing})

        if "lines" not in attrs:
            return attrs

        lines = attrs.get("lines", [])
        if len(lines) < 2:
            raise serializers.ValidationError({"lines": "A journal entry requires at least two lines."})

        total_debits = sum(line["amount"] for line in lines if line["side"] == JournalLine.Side.DEBIT)
        total_credits = sum(line["amount"] for line in lines if line["side"] == JournalLine.Side.CREDIT)
        if total_debits != total_credits:
            raise serializers.ValidationError({"lines": "Journal entry must balance: total debits must equal total credits."})

        if total_debits == 0:
            raise serializers.ValidationError({"lines": "Journal entry must include non-zero debit and credit totals."})

        return attrs

    def _line_inputs(self) -> list[JournalLineInput]:
        return [JournalLineInput(**line) for line in self.validated_data.get("lines", [])]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return create_draft_journal_entry(
            entry_date=validated_data["date"],
            description=validated_data["description"],
            lines=self._line_inputs(),
            created_by=user if getattr(user, "is_authenticated", False) else None,
            source=validated_data.get("source", "manual"),
        )

    def update(self, instance: JournalEntry, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return update_draft_journal_entry(
            entry=instance,
            entry_date=validated_data.get("date"),
            description=validated_data.get("description"),
            lines=self._line_inputs() if "lines" in validated_data else None,
            user=user if getattr(user, "is_authenticated", False) else None,
            source=validated_data.get("source", instance.source),
        )


class PostJournalEntrySerializer(serializers.Serializer):
    def save(self, **kwargs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return post_journal_entry(
            entry=self.context["entry"],
            user=user if getattr(user, "is_authenticated", False) else None,
            source="api",
        )


class ReverseJournalEntrySerializer(serializers.Serializer):
    reversal_date = serializers.DateField(required=False)
    description = serializers.CharField(required=False, allow_blank=True)

    def save(self, **kwargs):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        return reverse_journal_entry(
            entry=self.context["entry"],
            reversal_date=self.validated_data.get("reversal_date") or date.today(),
            user=user if getattr(user, "is_authenticated", False) else None,
            source="api",
            description=self.validated_data.get("description") or None,
        )


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ["id", "action", "record_type", "record_id", "source", "timestamp", "metadata"]
        read_only_fields = fields
