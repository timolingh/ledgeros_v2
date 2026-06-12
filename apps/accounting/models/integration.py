from __future__ import annotations

from django.db import models

from .accounts import Entity


class ApiRequestRecord(models.Model):
    """Persisted API submission used for idempotency and response replay."""

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="api_request_records")
    client_id = models.CharField(max_length=128)
    event_type = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=255)
    nonce = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    request_payload = models.JSONField(default=dict)
    response_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    response_payload = models.JSONField(default=dict, blank=True)
    domain_object_type = models.CharField(max_length=128, blank=True, default="")
    domain_object_id = models.CharField(max_length=64, blank=True, default="")
    journal_entry_id = models.CharField(max_length=64, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "client_id", "event_type", "idempotency_key"],
                name="unique_api_request_idempotency_per_client_entity_event",
            ),
            models.UniqueConstraint(fields=["client_id", "nonce"], name="unique_api_request_nonce_per_client"),
        ]

    def __str__(self) -> str:
        return f"{self.client_id}:{self.event_type}:{self.idempotency_key}"
