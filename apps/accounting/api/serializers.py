from __future__ import annotations

from datetime import date

from rest_framework import serializers

from apps.accounting.models import Account, AccountingPeriod, AuditLog, Entity, JournalEntry, JournalLine
from apps.accounting.services import JournalLineInput, post_journal_entry, reverse_journal_entry, update_draft_journal_entry
from apps.accounting.services.entities import get_default_entity
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
        return str(obj.posted_balance())

    def create(self, validated_data):
        return save_account(entity=get_default_entity(), **validated_data)

    def update(self, instance, validated_data):
        return save_account(account=instance, entity=instance.entity, **validated_data)


class AccountingPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccountingPeriod
        fields = ["id", "name", "start_date", "end_date", "status", "closed_at", "locked_at", "created_at", "updated_at"]
        read_only_fields = ["id", "status", "closed_at", "locked_at", "created_at", "updated_at"]

    def update(self, instance, validated_data):
        return save_accounting_period(period=instance, entity=instance.entity, **validated_data)


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
    date = serializers.DateField()
    description = serializers.CharField()
    source = serializers.CharField(required=False, default="manual")
    lines = JournalLineInputSerializer(many=True)

    def validate(self, attrs):
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
        return [JournalLineInput(**line) for line in self.validated_data["lines"]]

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
