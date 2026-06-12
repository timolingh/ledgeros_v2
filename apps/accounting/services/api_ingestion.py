from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounting.models import ApiRequestRecord, Bill, BillLine, CreditMemo, Customer, Entity, Invoice, InvoiceLine, JournalEntry, Payment, Vendor
from apps.accounting.services.ar_ap import apply_payment_to_bill, apply_payment_to_invoice, issue_customer_credit, issue_vendor_credit, post_bill, post_invoice
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.writes import get_or_create_undeposited_funds_account


@dataclass(frozen=True)
class ApiClientConfig:
    client_id: str
    enabled: bool
    secret_env: str
    scopes: tuple[str, ...]
    allowed_event_types: tuple[str, ...]
    api_key_env: str | None = None


def _ensure_mapping(data: Any, *, error_message: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValidationError(error_message)
    return data


def load_api_client_configs(path: str | Path | None = None) -> dict[str, ApiClientConfig]:
    raw_path = path or os.getenv("LEDGEROS_API_CLIENTS_CONFIG", "")
    if not raw_path:
        return {}
    config_path = Path(raw_path).expanduser()
    if not config_path.exists():
        raise ValidationError(f"API client config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    data = _ensure_mapping(raw, error_message="API client YAML must be a mapping.")

    api_clients = data.get("api_clients")
    if not isinstance(api_clients, list) or not api_clients:
        raise ValidationError("API client YAML must contain a non-empty api_clients list.")

    configs: dict[str, ApiClientConfig] = {}
    for index, item in enumerate(api_clients, start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"API client entry {index} must be a mapping.")

        client_id = str(item.get("client_id", "")).strip()
        enabled = bool(item.get("enabled", True))
        secret_env = str(item.get("secret_env", "")).strip()
        api_key_env = str(item.get("api_key_env", "")).strip() or None
        scopes = item.get("scopes")
        allowed_event_types = item.get("allowed_event_types")

        if not client_id:
            raise ValidationError(f"API client entry {index} requires client_id.")
        if client_id in configs:
            raise ValidationError(f"Duplicate API client_id in YAML: {client_id}")
        if not secret_env:
            raise ValidationError(f"API client {client_id} requires secret_env.")
        if not isinstance(scopes, list) or not scopes:
            raise ValidationError(f"API client {client_id} requires a non-empty scopes list.")
        if not isinstance(allowed_event_types, list) or not allowed_event_types:
            raise ValidationError(f"API client {client_id} requires a non-empty allowed_event_types list.")

        secret_value = os.getenv(secret_env)
        if not secret_value:
            raise ValidationError(f"API client {client_id} secret env var is missing: {secret_env}")
        if api_key_env and not os.getenv(api_key_env):
            raise ValidationError(f"API client {client_id} API key env var is missing: {api_key_env}")

        configs[client_id] = ApiClientConfig(
            client_id=client_id,
            enabled=enabled,
            secret_env=secret_env,
            scopes=tuple(str(scope).strip() for scope in scopes if str(scope).strip()),
            allowed_event_types=tuple(str(event_type).strip() for event_type in allowed_event_types if str(event_type).strip()),
            api_key_env=api_key_env,
        )

        if not configs[client_id].scopes:
            raise ValidationError(f"API client {client_id} requires at least one non-empty scope.")
        if not configs[client_id].allowed_event_types:
            raise ValidationError(f"API client {client_id} requires at least one non-empty allowed event type.")

    return configs


def get_api_client_config(client_id: str) -> ApiClientConfig:
    try:
        return load_api_client_configs()[client_id]
    except KeyError as exc:
        raise ValidationError(f"Unknown API client: {client_id}") from exc


def canonicalize_payload(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def hash_payload(payload: Any) -> str:
    return hashlib.sha256(canonicalize_payload(payload).encode("utf-8")).hexdigest()


def json_safe_payload(payload: Any) -> Any:
    return json.loads(canonicalize_payload(payload))


def _next_document_number(*, entity: Entity, prefix: str, queryset, field_name: str) -> str:
    highest = 0
    for current in queryset.values_list(field_name, flat=True):
        if not current.startswith(prefix):
            continue
        suffix = current[len(prefix) :]
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1:04d}"


def generate_invoice_number(*, entity: Entity) -> str:
    return _next_document_number(entity=entity, prefix="API-INV-", queryset=Invoice.objects.filter(entity=entity), field_name="invoice_number")


def generate_bill_number(*, entity: Entity) -> str:
    return _next_document_number(entity=entity, prefix="API-BILL-", queryset=Bill.objects.filter(entity=entity), field_name="bill_number")


def _find_customer(*, entity: Entity, customer_code: str) -> Customer:
    try:
        return Customer.objects.get(entity=entity, customer_code=customer_code)
    except Customer.DoesNotExist as exc:
        raise ValidationError({"customer_code": "Unknown customer."}) from exc


def _find_vendor(*, entity: Entity, vendor_code: str) -> Vendor:
    try:
        return Vendor.objects.get(entity=entity, vendor_code=vendor_code)
    except Vendor.DoesNotExist as exc:
        raise ValidationError({"vendor_code": "Unknown vendor."}) from exc


def _find_invoice_by_reference(*, entity: Entity, client_id: str, external_invoice_number: str) -> Invoice:
    try:
        return Invoice.objects.get(entity=entity, external_source_client_id=client_id, external_invoice_number=external_invoice_number)
    except Invoice.DoesNotExist as exc:
        raise ValidationError({"source_reference": "Unknown invoice reference."}) from exc


def _find_bill_by_reference(*, entity: Entity, client_id: str, external_bill_number: str) -> Bill:
    try:
        return Bill.objects.get(entity=entity, external_source_client_id=client_id, external_bill_number=external_bill_number)
    except Bill.DoesNotExist as exc:
        raise ValidationError({"source_reference": "Unknown bill reference."}) from exc


def _build_invoice_payload(invoice: Invoice, *, journal_entry: JournalEntry, client_id: str) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "invoice": {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "external_invoice_number": invoice.external_invoice_number,
            "external_source_client_id": invoice.external_source_client_id,
            "status": invoice.status,
            "customer_code": invoice.customer.customer_code,
            "date": str(invoice.date),
            "due_date": str(invoice.due_date),
            "total_amount": str(invoice.total_amount),
        },
        "journal_entry": {
            "id": journal_entry.id,
            "status": journal_entry.status,
        },
    }


def _build_bill_payload(bill: Bill, *, journal_entry: JournalEntry, client_id: str) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "bill": {
            "id": bill.id,
            "bill_number": bill.bill_number,
            "external_bill_number": bill.external_bill_number,
            "external_source_client_id": bill.external_source_client_id,
            "status": bill.status,
            "vendor_code": bill.vendor.vendor_code,
            "date": str(bill.date),
            "due_date": str(bill.due_date),
            "total_amount": str(bill.total_amount),
        },
        "journal_entry": {
            "id": journal_entry.id,
            "status": journal_entry.status,
        },
    }


def _build_payment_payload(*, payment: Payment, application, journal_entry: JournalEntry, client_id: str) -> dict[str, Any]:
    target = application.invoice or application.bill
    target_key = "invoice" if application.invoice else "bill"
    return {
        "client_id": client_id,
        "payment": {
            "id": payment.id,
            "source_type": payment.source_type,
            "source_id": payment.source_id,
            "amount": str(payment.amount),
            "payment_date": str(payment.payment_date),
            "is_credit_adjustment": payment.is_credit_adjustment,
        },
        "application": {
            "id": application.id,
            "applied_amount": str(application.applied_amount),
            target_key: {
                "id": target.id,
                "number": target.invoice_number if target_key == "invoice" else target.bill_number,
            },
        },
        "journal_entry": {
            "id": journal_entry.id,
            "status": journal_entry.status,
        },
    }


def _build_credit_payload(*, credit: CreditMemo, journal_entry: JournalEntry, client_id: str, event_label: str) -> dict[str, Any]:
    target = credit.customer or credit.vendor
    target_key = "customer" if credit.customer else "vendor"
    return {
        "client_id": client_id,
        "event_type": event_label,
        "credit_memo": {
            "id": credit.id,
            "type": credit.type,
            "amount": str(credit.amount),
            "memo_date": str(credit.memo_date),
            "reason": credit.reason,
            target_key: {
                "code": target.customer_code if credit.customer else target.vendor_code,
                "name": target.name,
            },
        },
        "journal_entry": {
            "id": journal_entry.id,
            "status": journal_entry.status,
        },
    }


def _submit_api_request(
    *,
    entity: Entity,
    client_id: str,
    event_type: str,
    idempotency_key: str,
    nonce: str,
    request_payload: dict[str, Any],
    create_response,
) -> tuple[int, dict[str, Any]]:
    request_hash = hash_payload(request_payload)

    existing = ApiRequestRecord.objects.filter(
        entity=entity,
        client_id=client_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
    ).first()
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ValidationError({"idempotency_key": "This idempotency key was already used with a different payload."})
        if existing.response_status_code is None:
            raise ValidationError({"idempotency_key": "This request is still processing."})
        return existing.response_status_code, existing.response_payload

    try:
        record = ApiRequestRecord.objects.create(
            entity=entity,
            client_id=client_id,
            event_type=event_type,
            idempotency_key=idempotency_key,
            nonce=nonce,
            request_hash=request_hash,
            request_payload=json_safe_payload(request_payload),
        )
    except IntegrityError as exc:
        raise ValidationError({"nonce": "This nonce has already been used."}) from exc

    status_code, response_payload, domain_object_type, domain_object_id, journal_entry_id = create_response()
    record.response_status_code = status_code
    record.response_payload = response_payload
    record.domain_object_type = domain_object_type
    record.domain_object_id = str(domain_object_id)
    record.journal_entry_id = str(journal_entry_id or "")
    record.save(update_fields=["response_status_code", "response_payload", "domain_object_type", "domain_object_id", "journal_entry_id", "updated_at"])
    audit_success(
        action=f"api_{event_type}_submitted",
        record=record,
        user=None,
        source="api",
        metadata={
            "client_id": client_id,
            "event_type": event_type,
            "idempotency_key": idempotency_key,
            "domain_object_type": domain_object_type,
            "domain_object_id": str(domain_object_id),
            "journal_entry_id": str(journal_entry_id or ""),
        },
    )
    return status_code, response_payload


@transaction.atomic
def submit_invoice_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    customer = _find_customer(entity=entity, customer_code=payload["customer_code"])
    lines_payload = payload["lines"]
    total_amount = sum((Decimal(str(line["amount"])) for line in lines_payload), Decimal("0.00"))
    if Decimal(str(payload["total_amount"])) != total_amount:
        raise ValidationError({"total_amount": "Invoice total does not match the sum of its lines."})

    def create_response():
        invoice = Invoice.objects.create(
            entity=entity,
            customer=customer,
            invoice_number=generate_invoice_number(entity=entity),
            external_invoice_number=payload["external_invoice_number"],
            external_source_client_id=client_id,
            date=payload["invoice_date"],
            due_date=payload["due_date"],
            total_amount=Decimal(str(payload["total_amount"])),
        )
        for line in lines_payload:
            InvoiceLine.objects.create(
                invoice=invoice,
                account_id=line["account_id"],
                line_description=line.get("line_description", ""),
                amount=Decimal(str(line["amount"])),
            )
        journal_entry = post_invoice(invoice=invoice, source="api")
        response_payload = _build_invoice_payload(invoice, journal_entry=journal_entry, client_id=client_id)
        return 201, response_payload, "Invoice", invoice.id, journal_entry.id

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type="invoice.post_requested",
        idempotency_key=idempotency_key,
        nonce=nonce,
        request_payload=payload,
        create_response=create_response,
    )


@transaction.atomic
def submit_bill_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    vendor = _find_vendor(entity=entity, vendor_code=payload["vendor_code"])
    lines_payload = payload["lines"]
    total_amount = sum((Decimal(str(line["amount"])) for line in lines_payload), Decimal("0.00"))
    if Decimal(str(payload["total_amount"])) != total_amount:
        raise ValidationError({"total_amount": "Bill total does not match the sum of its lines."})

    def create_response():
        bill = Bill.objects.create(
            entity=entity,
            vendor=vendor,
            bill_number=generate_bill_number(entity=entity),
            external_bill_number=payload["external_bill_number"],
            external_source_client_id=client_id,
            date=payload["bill_date"],
            due_date=payload["due_date"],
            total_amount=Decimal(str(payload["total_amount"])),
        )
        for line in lines_payload:
            BillLine.objects.create(
                bill=bill,
                account_id=line["account_id"],
                line_description=line.get("line_description", ""),
                amount=Decimal(str(line["amount"])),
            )
        journal_entry = post_bill(bill=bill, source="api")
        response_payload = _build_bill_payload(bill, journal_entry=journal_entry, client_id=client_id)
        return 201, response_payload, "Bill", bill.id, journal_entry.id

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type="bill.post_requested",
        idempotency_key=idempotency_key,
        nonce=nonce,
        request_payload=payload,
        create_response=create_response,
    )


@transaction.atomic
def submit_payment_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    source_type = payload["source_type"]
    source_reference = payload["source_reference"]
    amount = Decimal(str(payload["amount"]))

    def create_response():
        if source_type == Payment.SourceType.INVOICE:
            invoice = _find_invoice_by_reference(entity=entity, client_id=client_id, external_invoice_number=source_reference)
            if amount > invoice.outstanding_balance():
                raise ValidationError({"amount": "Payment amount cannot exceed the invoice outstanding balance."})
            payment = Payment.objects.create(
                entity=entity,
                source_type=Payment.SourceType.INVOICE,
                source_id=invoice.id,
                amount=amount,
                payment_date=payload["payment_date"],
                account=get_or_create_undeposited_funds_account(entity=entity),
            )
            application, journal_entry = apply_payment_to_invoice(payment=payment, invoice=invoice, applied_amount=amount, source="api")
        else:
            bill = _find_bill_by_reference(entity=entity, client_id=client_id, external_bill_number=source_reference)
            if amount > bill.outstanding_balance():
                raise ValidationError({"amount": "Payment amount cannot exceed the bill outstanding balance."})
            payment = Payment.objects.create(
                entity=entity,
                source_type=Payment.SourceType.BILL,
                source_id=bill.id,
                amount=amount,
                payment_date=payload["payment_date"],
                account=get_or_create_undeposited_funds_account(entity=entity),
            )
            application, journal_entry = apply_payment_to_bill(payment=payment, bill=bill, applied_amount=amount, source="api")
        response_payload = _build_payment_payload(payment=payment, application=application, journal_entry=journal_entry, client_id=client_id)
        return 201, response_payload, "Payment", payment.id, journal_entry.id

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type="payment.post_requested",
        idempotency_key=idempotency_key,
        nonce=nonce,
        request_payload=payload,
        create_response=create_response,
    )


@transaction.atomic
def submit_credit_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any], event_type: str = "credit.post_requested") -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    source_type = payload["source_type"]
    source_reference = payload["source_reference"]
    amount = Decimal(str(payload["amount"]))
    reason = payload.get("reason", "")
    if source_type not in {Payment.SourceType.INVOICE, Payment.SourceType.BILL}:
        raise ValidationError({"source_type": "Invalid source type."})

    def create_response():
        if source_type == Payment.SourceType.INVOICE:
            invoice = _find_invoice_by_reference(entity=entity, client_id=client_id, external_invoice_number=source_reference)
            credit, journal_entry = issue_customer_credit(invoice=invoice, amount=amount, reason=reason, source="api")
        else:
            bill = _find_bill_by_reference(entity=entity, client_id=client_id, external_bill_number=source_reference)
            credit, journal_entry = issue_vendor_credit(bill=bill, amount=amount, reason=reason, source="api")
        response_payload = _build_credit_payload(credit=credit, journal_entry=journal_entry, client_id=client_id, event_label=event_type)
        return 201, response_payload, "CreditMemo", credit.id, journal_entry.id

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type=event_type,
        idempotency_key=idempotency_key,
        nonce=nonce,
        request_payload=payload,
        create_response=create_response,
    )
