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


class SyncEventRecord(models.Model):
    """Generic inbound sync event persisted by LedgerOS for downstream integrations."""

    class Status(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"

    entity = models.ForeignKey(Entity, on_delete=models.PROTECT, related_name="sync_event_records")
    source_system = models.CharField(max_length=128)
    domain_event_type = models.CharField(max_length=128)
    external_id = models.CharField(max_length=255)
    source_object_type = models.CharField(max_length=128)
    source_object_id = models.CharField(max_length=128)
    idempotency_key = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    occurred_at = models.DateTimeField()
    payload = models.JSONField(default=dict)
    response_payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["entity", "source_system", "domain_event_type", "idempotency_key"],
                name="unique_sync_event_idempotency_per_source_event",
            ),
            models.UniqueConstraint(
                fields=["entity", "source_system", "domain_event_type", "external_id"],
                name="unique_sync_event_external_id_per_source_event",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_system}:{self.domain_event_type}:{self.external_id}"
