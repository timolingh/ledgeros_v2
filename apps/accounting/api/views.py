from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
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
from apps.accounting.services.periods import change_period_status, create_accounting_period
from apps.accounting.services.entities import get_default_entity


def raise_drf_validation(exc: DjangoValidationError) -> None:
    raise DRFValidationError(getattr(exc, "message_dict", None) or getattr(exc, "messages", None) or str(exc))


class DefaultEntityScopedMixin:
    def get_entity(self) -> Entity:
        return get_default_entity()


class EntityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EntitySerializer
    queryset = Entity.objects.all().order_by("id")


class AccountViewSet(DefaultEntityScopedMixin, viewsets.ModelViewSet):
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


class AccountingPeriodViewSet(DefaultEntityScopedMixin, viewsets.ModelViewSet):
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


class JournalEntryViewSet(DefaultEntityScopedMixin, viewsets.ModelViewSet):
    def get_queryset(self):
        return JournalEntry.objects.filter(entity=self.get_entity()).prefetch_related("lines__account").order_by("-date", "-id")

    def get_serializer_class(self):
        if self.action in {"create", "update", "partial_update"}:
            return JournalEntryWriteSerializer
        return JournalEntrySerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            entry = serializer.save()
        except DjangoValidationError as exc:
            raise_drf_validation(exc)
        return Response(JournalEntrySerializer(entry, context=self.get_serializer_context()).data, status=status.HTTP_201_CREATED)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
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
