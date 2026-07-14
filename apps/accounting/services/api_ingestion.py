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

from apps.accounting.models import (
    ApiRequestRecord,
    Account,
    Bill,
    BillLine,
    CreditMemo,
    Customer,
    Entity,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    Payment,
    SyncEventRecord,
    Vendor,
)
from apps.accounting.services.ar_ap import apply_payment_to_bill, apply_payment_to_invoice, issue_customer_credit, issue_vendor_credit, post_bill, post_invoice
from apps.accounting.services.audit import audit_success
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.posting import JournalLineInput, create_and_post_journal_entry
from apps.accounting.services.writes import get_or_create_cash_account


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


def _build_customer_payload(customer: Customer, *, client_id: str) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "customer": {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "name": customer.name,
            "status": customer.status,
            "default_ar_account_code": (
                customer.default_ar_account.account_code if customer.default_ar_account_id else ""
            ),
            "default_ar_account_name": (
                customer.default_ar_account.name if customer.default_ar_account_id else ""
            ),
        },
    }


def _find_vendor(*, entity: Entity, vendor_code: str) -> Vendor:
    try:
        return Vendor.objects.get(entity=entity, vendor_code=vendor_code)
    except Vendor.DoesNotExist as exc:
        raise ValidationError({"vendor_code": "Unknown vendor."}) from exc


def _build_vendor_payload(vendor: Vendor, *, client_id: str) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "vendor": {
            "id": vendor.id,
            "vendor_code": vendor.vendor_code,
            "name": vendor.name,
            "status": vendor.status,
            "default_ap_account_code": (
                vendor.default_ap_account.account_code if vendor.default_ap_account_id else ""
            ),
            "default_ap_account_name": (
                vendor.default_ap_account.name if vendor.default_ap_account_id else ""
            ),
        },
    }


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


def _build_sync_event_payload(sync_event: SyncEventRecord, *, client_id: str) -> dict[str, Any]:
    return {
        "client_id": client_id,
        "sync_event": {
            "id": sync_event.id,
            "source_system": sync_event.source_system,
            "domain_event_type": sync_event.domain_event_type,
            "external_id": sync_event.external_id,
            "source_object_type": sync_event.source_object_type,
            "source_object_id": sync_event.source_object_id,
            "occurred_at": sync_event.occurred_at.isoformat(),
            "status": sync_event.status,
        },
    }


def _resolve_sync_event_journal_lines(*, entity: Entity, accounting_entries: list[dict[str, Any]]) -> list[JournalLineInput]:
    resolved: list[JournalLineInput] = []
    for index, entry in enumerate(accounting_entries, start=1):
        if not isinstance(entry, dict):
            raise ValidationError({f"accounting_entries[{index}]": "Each accounting entry must be an object."})
        account_code = str(entry.get("account_code", "")).strip()
        if not account_code:
            raise ValidationError({f"accounting_entries[{index}].account_code": "This field is required."})
        side = str(entry.get("direction", "")).strip().lower()
        if side not in JournalLine.Side.values:
            raise ValidationError({f"accounting_entries[{index}].direction": "Enter debit or credit."})
        try:
            account = Account.objects.get(entity=entity, account_code=account_code, is_active=True)
        except Account.DoesNotExist as exc:
            raise ValidationError({f"accounting_entries[{index}].account_code": "Active account not found for code."}) from exc
        resolved.append(
            JournalLineInput(
                account_code=account.account_code,
                side=side,
                amount=Decimal(str(entry.get("amount"))),
                description=str(entry.get("line_description", "")),
            )
        )
    return resolved


@transaction.atomic
def submit_customer_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    customer_code = payload["customer_code"]
    customer_defaults: dict[str, Any] = {
        "name": payload["name"],
        "status": payload.get("status", Customer.Status.ACTIVE),
    }
    if payload.get("default_ar_account"):
        customer_defaults["default_ar_account"] = payload["default_ar_account"]

    def create_response():
        customer, created = Customer.objects.get_or_create(
            entity=entity,
            customer_code=customer_code,
            defaults=customer_defaults,
        )
        if not created:
            customer.name = payload["name"]
            customer.status = payload.get("status", customer.status)
            if payload.get("default_ar_account"):
                customer.default_ar_account = payload["default_ar_account"]
            elif customer.default_ar_account_id is None:
                raise ValidationError(
                    {
                        "default_ar_account_code": (
                            "A default AR account code is required when creating a customer."
                        )
                    }
                )
            customer.full_clean()
            customer.save()
        elif customer.default_ar_account_id is None:
            raise ValidationError(
                {
                    "default_ar_account_code": (
                        "A default AR account code is required when creating a customer."
                    )
                }
            )

        response_payload = _build_customer_payload(customer, client_id=client_id)
        return 201 if created else 200, response_payload, "Customer", customer.id, None

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type="customer.upsert_requested",
        idempotency_key=idempotency_key,
        nonce=nonce,
        request_payload=payload,
        create_response=create_response,
    )


@transaction.atomic
def submit_vendor_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    vendor_code = payload["vendor_code"]
    vendor_defaults: dict[str, Any] = {
        "name": payload["name"],
        "status": payload.get("status", Vendor.Status.ACTIVE),
    }
    if payload.get("default_ap_account"):
        vendor_defaults["default_ap_account"] = payload["default_ap_account"]

    def create_response():
        vendor, created = Vendor.objects.get_or_create(
            entity=entity,
            vendor_code=vendor_code,
            defaults=vendor_defaults,
        )
        if not created:
            vendor.name = payload["name"]
            vendor.status = payload.get("status", vendor.status)
            if payload.get("default_ap_account"):
                vendor.default_ap_account = payload["default_ap_account"]
            elif vendor.default_ap_account_id is None:
                raise ValidationError(
                    {
                        "default_ap_account_code": (
                            "A default AP account code is required when creating a vendor."
                        )
                    }
                )
            vendor.full_clean()
            vendor.save()
        elif vendor.default_ap_account_id is None:
            raise ValidationError(
                {
                    "default_ap_account_code": (
                        "A default AP account code is required when creating a vendor."
                    )
                }
            )

        response_payload = _build_vendor_payload(vendor, client_id=client_id)
        return 201 if created else 200, response_payload, "Vendor", vendor.id, None

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type="vendor.upsert_requested",
        idempotency_key=idempotency_key,
        nonce=nonce,
        request_payload=payload,
        create_response=create_response,
    )


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
                account=get_or_create_cash_account(entity=entity),
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
                account=get_or_create_cash_account(entity=entity),
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
def submit_sync_event(*, client_id: str, idempotency_key: str, nonce: str, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    entity = get_default_entity()
    payload_body = payload.get("payload")
    accounting_entries = payload_body.get("accounting_entries") if isinstance(payload_body, dict) else None

    def create_response():
        sync_event, created = SyncEventRecord.objects.get_or_create(
            entity=entity,
            source_system=payload["source_system"],
            domain_event_type=payload["domain_event_type"],
            external_id=payload["external_id"],
            defaults={
                "source_object_type": payload["source_object_type"],
                "source_object_id": payload["source_object_id"],
                "idempotency_key": idempotency_key,
                "request_hash": hash_payload(payload),
                "occurred_at": payload["occurred_at"],
                "payload": json_safe_payload(payload["payload"]),
            },
        )
        if not created:
            incoming_hash = hash_payload(payload)
            if (
                sync_event.source_object_type != payload["source_object_type"]
                or sync_event.source_object_id != payload["source_object_id"]
                or sync_event.occurred_at != payload["occurred_at"]
                or sync_event.request_hash != incoming_hash
            ):
                raise ValidationError({"external_id": "This external id already exists with different data."})

        response_payload = _build_sync_event_payload(sync_event, client_id=client_id)
        if isinstance(accounting_entries, list) and accounting_entries:
            journal_lines = _resolve_sync_event_journal_lines(entity=entity, accounting_entries=accounting_entries)
            if len(journal_lines) < 2:
                raise ValidationError({"accounting_entries": "At least two accounting entries are required."})
            journal_entry = create_and_post_journal_entry(
                entry_date=payload["occurred_at"].date(),
                description=payload["domain_event_type"],
                lines=journal_lines,
                source="api",
            )
            sync_event.status = SyncEventRecord.Status.PROCESSED
            response_payload["journal_entry"] = {
                "id": journal_entry.id,
                "status": journal_entry.status,
            }
            sync_event.save(update_fields=["status", "updated_at"])
        sync_event.response_payload = response_payload
        sync_event.save(update_fields=["response_payload", "updated_at"])
        return 201 if created else 200, response_payload, "SyncEventRecord", sync_event.id, response_payload.get("journal_entry", {}).get("id")

    return _submit_api_request(
        entity=entity,
        client_id=client_id,
        event_type="sync.event_received",
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
