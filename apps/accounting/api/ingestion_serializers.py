from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.accounting.models import Account, Customer, Vendor
from apps.accounting.services.entities import get_default_entity


class ApiLineInputSerializer(serializers.Serializer):
    account_code = serializers.CharField(max_length=32)
    line_description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class _ApiDocumentBaseSerializer(serializers.Serializer):
    def _resolve_lines(self, lines_data):
        entity = get_default_entity()
        resolved = []
        for index, line in enumerate(lines_data, start=1):
            try:
                account = Account.objects.get(entity=entity, account_code=line["account_code"])
            except Account.DoesNotExist as exc:
                raise serializers.ValidationError({f"lines[{index}].account_code": "Unknown account code."}) from exc
            if not account.is_active:
                raise serializers.ValidationError({f"lines[{index}].account_code": "Account must be active."})
            resolved.append(
                {
                    "account_id": account.id,
                    "account_code": account.account_code,
                    "line_description": line.get("line_description", ""),
                    "amount": line["amount"],
                }
            )
        return resolved

    def _validate_total(self, *, total_amount: Decimal, lines) -> None:
        calculated_total = sum((Decimal(str(line["amount"])) for line in lines), Decimal("0.00"))
        if Decimal(str(total_amount)) != calculated_total:
            raise serializers.ValidationError({"total_amount": "Total amount must equal the sum of the line amounts."})


class ApiInvoiceCreateSerializer(_ApiDocumentBaseSerializer):
    customer_code = serializers.CharField(max_length=64)
    external_invoice_number = serializers.CharField(max_length=255)
    invoice_date = serializers.DateField()
    due_date = serializers.DateField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    lines = ApiLineInputSerializer(many=True)

    def validate(self, attrs):
        if not attrs["lines"]:
            raise serializers.ValidationError({"lines": "At least one line is required."})
        attrs["lines"] = self._resolve_lines(attrs["lines"])
        self._validate_total(total_amount=attrs["total_amount"], lines=attrs["lines"])
        if attrs["due_date"] < attrs["invoice_date"]:
            raise serializers.ValidationError({"due_date": "Due date must be on or after the invoice date."})
        return attrs


class ApiBillCreateSerializer(_ApiDocumentBaseSerializer):
    vendor_code = serializers.CharField(max_length=64)
    external_bill_number = serializers.CharField(max_length=255)
    bill_date = serializers.DateField()
    due_date = serializers.DateField()
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    lines = ApiLineInputSerializer(many=True)

    def validate(self, attrs):
        if not attrs["lines"]:
            raise serializers.ValidationError({"lines": "At least one line is required."})
        attrs["lines"] = self._resolve_lines(attrs["lines"])
        self._validate_total(total_amount=attrs["total_amount"], lines=attrs["lines"])
        if attrs["due_date"] < attrs["bill_date"]:
            raise serializers.ValidationError({"due_date": "Due date must be on or after the bill date."})
        return attrs


class ApiPaymentCreateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=["invoice", "bill"])
    source_reference = serializers.CharField(max_length=255)
    payment_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class ApiCreditCreateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=["invoice", "bill"])
    source_reference = serializers.CharField(max_length=255)
    credit_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ApiBankTransactionCreateSerializer(serializers.Serializer):
    bank_account_id = serializers.IntegerField()
    transaction_date = serializers.DateField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    offset_account_code = serializers.CharField(max_length=32)
    memo = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")


class ApiCustomerUpsertSerializer(serializers.Serializer):
    customer_code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=255)
    default_ar_account_code = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
    )
    status = serializers.ChoiceField(
        choices=Customer.Status.choices,
        required=False,
        default=Customer.Status.ACTIVE,
    )

    def validate(self, attrs):
        account_code = str(attrs.get("default_ar_account_code", "")).strip()
        if not account_code:
            return attrs

        entity = get_default_entity()
        try:
            account = Account.objects.get(entity=entity, account_code=account_code)
        except Account.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"default_ar_account_code": "Unknown account code."}
            ) from exc

        if not account.is_active:
            raise serializers.ValidationError(
                {"default_ar_account_code": "Account must be active."}
            )

        attrs["default_ar_account"] = account
        attrs["default_ar_account_code"] = account.account_code
        return attrs


class ApiVendorUpsertSerializer(serializers.Serializer):
    vendor_code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=255)
    default_ap_account_code = serializers.CharField(
        max_length=32,
        required=False,
        allow_blank=True,
        default="",
    )
    status = serializers.ChoiceField(
        choices=Vendor.Status.choices,
        required=False,
        default=Vendor.Status.ACTIVE,
    )

    def validate(self, attrs):
        account_code = str(attrs.get("default_ap_account_code", "")).strip()
        if not account_code:
            return attrs

        entity = get_default_entity()
        try:
            account = Account.objects.get(entity=entity, account_code=account_code)
        except Account.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"default_ap_account_code": "Unknown account code."}
            ) from exc

        if not account.is_active:
            raise serializers.ValidationError(
                {"default_ap_account_code": "Account must be active."}
            )

        attrs["default_ap_account"] = account
        attrs["default_ap_account_code"] = account.account_code
        return attrs


class ApiSyncEventSerializer(serializers.Serializer):
    source_system = serializers.CharField(max_length=128)
    domain_event_type = serializers.CharField(max_length=128)
    external_id = serializers.CharField(max_length=255)
    source_object_type = serializers.CharField(max_length=128)
    source_object_id = serializers.CharField(max_length=128)
    occurred_at = serializers.DateTimeField()
    payload = serializers.JSONField()
