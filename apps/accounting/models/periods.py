from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .accounts import Entity


class AccountingPeriod(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SOFT_CLOSED = "soft_closed", "Soft closed"
        LOCKED = "locked", "Locked"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="periods")
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)
    name = models.CharField(max_length=128, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(start_date__lte=models.F("end_date")), name="period_start_before_end"),
            models.UniqueConstraint(fields=["entity", "start_date", "end_date"], name="unique_period_dates_per_entity"),
        ]
        ordering = ["start_date"]

    def __str__(self) -> str:
        return self.name or f"{self.start_date} to {self.end_date}"

    def contains(self, entry_date) -> bool:
        return self.start_date <= entry_date <= self.end_date

    @classmethod
    def find_for_date(cls, entity: Entity, entry_date):
        return cls.objects.filter(entity=entity, start_date__lte=entry_date, end_date__gte=entry_date).order_by("start_date").first()

    def assert_posting_allowed(self, *, allow_soft_closed: bool = False) -> None:
        if self.status == self.Status.LOCKED:
            raise ValidationError("Locked accounting periods reject postings.")
        if self.status == self.Status.SOFT_CLOSED and not allow_soft_closed:
            raise ValidationError("Soft-closed accounting periods require elevated approval for posting.")

    def mark_soft_closed(self) -> None:
        if self.status == self.Status.LOCKED:
            raise ValidationError("Locked periods cannot be soft-closed.")
        self.status = self.Status.SOFT_CLOSED
        self.closed_at = timezone.now()
        self.save(update_fields=["status", "closed_at", "updated_at"])

    def mark_locked(self) -> None:
        self.status = self.Status.LOCKED
        self.locked_at = timezone.now()
        self.save(update_fields=["status", "locked_at", "updated_at"])

    def reopen(self) -> None:
        self.status = self.Status.OPEN
        self.save(update_fields=["status", "updated_at"])
