from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError as DRFValidationError
from rest_framework.response import Response

from apps.accounting.api.serializers import (
    AccountSerializer,
    AccountingPeriodSerializer,
    AuditLogSerializer,
    EntitySerializer,
    JournalEntrySerializer,
    JournalEntryWriteSerializer,
    PostJournalEntrySerializer,
    ReverseJournalEntrySerializer,
)
from apps.accounting.models import Account, AccountingPeriod, AuditLog, Entity, JournalEntry
from apps.accounting.services.entities import get_default_entity
from apps.accounting.services.periods import change_period_status, create_accounting_period


def raise_drf_validation(exc: DjangoValidationError) -> None:
    raise DRFValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc))


def request_has_field(request, field_name: str) -> bool:
    return field_name in getattr(request, "data", {})


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
