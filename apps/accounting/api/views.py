from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.exceptions import ValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.exceptions import MethodNotAllowed, ValidationError as DRFValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounting.api.authentication import ApiClientAuthentication
from apps.accounting.api.ingestion_serializers import (
    ApiBillCreateSerializer,
    ApiCreditCreateSerializer,
    ApiInvoiceCreateSerializer,
    ApiPaymentCreateSerializer,
)
from apps.accounting.api.serializers import (
    AccountSerializer,
    AccountingPeriodSerializer,
    AuditLogSerializer,
    EntitySerializer,
    JournalEntrySerializer,
    JournalEntryWriteSerializer,
    PostJournalEntrySerializer,
    ReverseJournalEntrySerializer,
    ReportViewSerializer,
    TaxCodeSerializer,
)
from apps.accounting.models import Account, AccountingPeriod, AuditLog, Entity, JournalEntry, ReportView, TaxCode
from apps.accounting.services.api_ingestion import submit_bill_event, submit_credit_event, submit_invoice_event, submit_payment_event
from apps.accounting.services.reporting import (
    generate_balance_sheet,
    generate_profit_and_loss,
    generate_report_drilldown,
    run_report_view,
    summarize_period,
    tax_summary,
)
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.periods import change_period_status, create_accounting_period


def raise_drf_validation(exc: DjangoValidationError) -> None:
    raise DRFValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc))


def request_has_field(request, field_name: str) -> bool:
    return field_name in getattr(request, "data", {})


def parse_query_date(request, field_name: str) -> date:
    value = request.query_params.get(field_name)
    if not value:
        raise DRFValidationError({field_name: "This query parameter is required."})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DRFValidationError({field_name: "Enter a valid date in YYYY-MM-DD format."}) from exc


def _get_idempotency_key(request) -> str:
    header_value = request.headers.get("Idempotency-Key", "").strip()
    if header_value:
        return header_value
    payload_value = str(request.data.get("idempotency_key", "")).strip()
    if payload_value:
        return payload_value
    raise DRFValidationError({"idempotency_key": "This field is required in the Idempotency-Key header or payload."})


class ApiSubmissionView(APIView):
    authentication_classes = [ApiClientAuthentication]
    permission_classes = [IsAuthenticated]
    serializer_class = None
    required_scope = ""
    event_type = ""
    service_func = None

    def _authorize_client(self, request) -> None:
        principal = request.user
        if self.required_scope not in getattr(principal, "scopes", ()):
            raise PermissionDenied("API client is not allowed to perform this action.")
        if self.event_type not in getattr(principal, "allowed_event_types", ()):
            raise PermissionDenied("API client is not allowed to submit this event type.")

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._authorize_client(request)
        idempotency_key = _get_idempotency_key(request)
        auth_context = request.auth
        nonce = getattr(auth_context, "nonce", "") or f"api-key:{self.event_type}:{idempotency_key}"
        try:
            response_status_code, response_payload = self.service_func(
                client_id=request.user.client_id,
                idempotency_key=idempotency_key,
                nonce=nonce,
                payload=serializer.validated_data,
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(response_payload, status=response_status_code)


class DefaultEntityScopedMixin:
    def get_entity(self) -> Entity:
        return get_default_entity()


class UnsafeMethodLimitedMixin:
    """Allow explicit create/update actions, but no generic PUT or DELETE writes."""

    http_method_names = ["get", "post", "patch", "head", "options"]

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed("DELETE")


class EntityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EntitySerializer
    queryset = Entity.objects.all().order_by("id")


class AccountViewSet(UnsafeMethodLimitedMixin, DefaultEntityScopedMixin, viewsets.ModelViewSet):
    serializer_class = AccountSerializer

    def get_queryset(self):
        return Account.objects.filter(entity=self.get_entity()).order_by("account_code")

    def perform_create(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)


class AccountingPeriodViewSet(UnsafeMethodLimitedMixin, DefaultEntityScopedMixin, viewsets.ModelViewSet):
    serializer_class = AccountingPeriodSerializer

    def get_queryset(self):
        return AccountingPeriod.objects.filter(entity=self.get_entity()).order_by("start_date")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            period = create_accounting_period(
                start_date=serializer.validated_data["start_date"],
                end_date=serializer.validated_data["end_date"],
                name=serializer.validated_data.get("name", ""),
                user=request.user,
                source="api",
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(self.get_serializer(period).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if request_has_field(request, "status"):
            raise DRFValidationError({"status": "Use the change_status action to change accounting period status."})
        partial = kwargs.pop("partial", False)
        period = self.get_object()
        serializer = self.get_serializer(period, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            period = serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["post"])
    def change_status(self, request, pk=None):
        period = self.get_object()
        status_value = request.data.get("status")
        reason = request.data.get("reason", "")
        try:
            period = change_period_status(period=period, status=status_value, user=request.user, source="api", reason=reason)
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(self.get_serializer(period).data)

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        period = self.get_object()
        return Response(summarize_period(period=period))


class JournalEntryViewSet(UnsafeMethodLimitedMixin, DefaultEntityScopedMixin, viewsets.ModelViewSet):
    def get_queryset(self):
        return JournalEntry.objects.filter(entity=self.get_entity()).prefetch_related("lines__account").order_by("-date", "-id")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return JournalEntryWriteSerializer
        return JournalEntrySerializer

    def create(self, request, *args, **kwargs):
        if request_has_field(request, "status"):
            raise DRFValidationError({"status": "Journal entries are created as drafts. Use the post action to post them."})
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entry = serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(JournalEntrySerializer(entry, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        if request_has_field(request, "status"):
            raise DRFValidationError({"status": "Use the post or reverse action to change journal entry status."})
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        if instance.status != JournalEntry.Status.DRAFT:
            raise DRFValidationError("Only draft journal entries may be edited through the API.")
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        try:
            entry = serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(JournalEntrySerializer(entry, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        entry = self.get_object()
        serializer = PostJournalEntrySerializer(data=request.data or {}, context={"request": request, "entry": entry})
        serializer.is_valid(raise_exception=True)
        try:
            entry = serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(JournalEntrySerializer(entry, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        entry = self.get_object()
        serializer = ReverseJournalEntrySerializer(data=request.data or {}, context={"request": request, "entry": entry})
        serializer.is_valid(raise_exception=True)
        try:
            reversal = serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(JournalEntrySerializer(reversal, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    queryset = AuditLog.objects.all().order_by("-timestamp", "-id")


class ReportViewSet(UnsafeMethodLimitedMixin, DefaultEntityScopedMixin, viewsets.ModelViewSet):
    serializer_class = ReportViewSerializer

    def get_queryset(self):
        return ReportView.objects.filter(entity=self.get_entity()).order_by("name", "id")

    def perform_create(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)

    @action(detail=True, methods=["post"])
    def run(self, request, pk=None):
        report_view = self.get_object()
        return Response(run_report_view(report_view=report_view))

    @action(detail=True, methods=["get"])
    def drilldown(self, request, pk=None):
        report_view = self.get_object()
        account_code = request.query_params.get("account_code")
        if not account_code:
            raise DRFValidationError({"account_code": "This query parameter is required."})

        try:
            if report_view.report_type == ReportView.ReportType.BALANCE_SHEET:
                return Response(
                    generate_report_drilldown(
                        entity=report_view.entity,
                        report_type=report_view.report_type,
                        account_code=account_code,
                        basis=report_view.basis,
                        as_of=report_view.as_of_date,
                    )
                )
            if report_view.report_type == ReportView.ReportType.PROFIT_AND_LOSS:
                return Response(
                    generate_report_drilldown(
                        entity=report_view.entity,
                        report_type=report_view.report_type,
                        account_code=account_code,
                        basis=report_view.basis,
                        start_date=report_view.start_date,
                        end_date=report_view.end_date,
                    )
                )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        raise DRFValidationError({"report_type": "Unsupported report type."})

    @action(detail=False, methods=["get"])
    def balance_sheet(self, request):
        try:
            return Response(generate_balance_sheet(entity=self.get_entity(), as_of=parse_query_date(request, "as_of")))
        except DjangoValidationError as exc:
            raise_drf_validation(exc)

    @action(detail=False, methods=["get"])
    def profit_and_loss(self, request):
        start_date = parse_query_date(request, "start_date")
        end_date = parse_query_date(request, "end_date")
        basis = request.query_params.get("basis", "accrual")
        try:
            return Response(
                generate_profit_and_loss(
                    entity=self.get_entity(),
                    start_date=start_date,
                    end_date=end_date,
                    basis=basis,
                )
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)

    @action(detail=False, methods=["get"])
    def tax_summary(self, request):
        return Response(tax_summary(entity=self.get_entity()))


class TaxCodeViewSet(UnsafeMethodLimitedMixin, DefaultEntityScopedMixin, viewsets.ModelViewSet):
    serializer_class = TaxCodeSerializer

    def get_queryset(self):
        return TaxCode.objects.filter(entity=self.get_entity()).order_by("code", "id")

    def perform_create(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)

    def perform_update(self, serializer):
        try:
            serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)


class InvoiceSubmissionView(ApiSubmissionView):
    serializer_class = ApiInvoiceCreateSerializer
    required_scope = "invoices"
    event_type = "invoice.post_requested"
    service_func = staticmethod(submit_invoice_event)


class BillSubmissionView(ApiSubmissionView):
    serializer_class = ApiBillCreateSerializer
    required_scope = "bills"
    event_type = "bill.post_requested"
    service_func = staticmethod(submit_bill_event)


class PaymentSubmissionView(ApiSubmissionView):
    serializer_class = ApiPaymentCreateSerializer
    required_scope = "payments"
    event_type = "payment.post_requested"
    service_func = staticmethod(submit_payment_event)


class CreditSubmissionView(ApiSubmissionView):
    serializer_class = ApiCreditCreateSerializer
    required_scope = "credits"
    event_type = "credit.post_requested"
    service_func = staticmethod(submit_credit_event)


class RefundSubmissionView(ApiSubmissionView):
    serializer_class = ApiCreditCreateSerializer
    required_scope = "credits"
    event_type = "refund.post_requested"

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        self._authorize_client(request)
        idempotency_key = _get_idempotency_key(request)
        auth_context = request.auth
        nonce = getattr(auth_context, "nonce", "") or f"api-key:{self.event_type}:{idempotency_key}"
        try:
            response_status_code, response_payload = submit_credit_event(
                client_id=request.user.client_id,
                idempotency_key=idempotency_key,
                nonce=nonce,
                payload=serializer.validated_data,
                event_type=self.event_type,
            )
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(response_payload, status=response_status_code)
