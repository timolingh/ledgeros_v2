from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from django.core.exceptions import ValidationError
from django.utils import timezone as django_timezone
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from apps.accounting.models import AuditLog
from apps.accounting.services.api_ingestion import get_api_client_config


HMAC_TIMESTAMP_SKEW_SECONDS = 300


@dataclass(frozen=True)
class ApiClientAuthContext:
    client_id: str
    auth_mode: str
    nonce: str
    timestamp: str
    request_hash: str


@dataclass(frozen=True)
class ApiClientPrincipal:
    client_id: str
    auth_mode: str
    scopes: tuple[str, ...]
    allowed_event_types: tuple[str, ...]

    @property
    def is_authenticated(self) -> bool:
        return True


def _audit_auth_failure(*, client_id: str, reason: str, path: str) -> None:
    try:
        AuditLog.objects.create(
            action="api_auth_failed",
            record_type="ApiClient",
            record_id=client_id or "unknown",
            source="api",
            metadata={
                "reason": reason,
                "path": path,
            },
        )
    except Exception:
        # Authentication must never fail because auditing failed.
        return


def _canonicalize_body(request) -> bytes:
    body = request._request.body or b""
    if not body:
        return b""
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AuthenticationFailed("Request body must be valid JSON.") from exc
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _build_signature_payload(*, client_id: str, method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
    body_hash = hashlib.sha256(body).hexdigest()
    canonical = "\n".join([client_id, method.upper(), path, timestamp, nonce, body_hash])
    return canonical.encode("utf-8")


def _validate_timestamp(timestamp_value: str) -> None:
    try:
        parsed = datetime.fromtimestamp(int(timestamp_value), tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise AuthenticationFailed("Invalid API request timestamp.") from exc
    now = django_timezone.now()
    if abs((now - parsed).total_seconds()) > HMAC_TIMESTAMP_SKEW_SECONDS:
        raise AuthenticationFailed("API request timestamp is outside the allowed skew.")


class ApiClientAuthentication(BaseAuthentication):
    def authenticate(self, request):
        client_id = request.headers.get("X-LedgerOS-Client-Id", "").strip()
        if not client_id:
            _audit_auth_failure(client_id="unknown", reason="missing_client_id", path=request.path)
            raise AuthenticationFailed("Missing API client id.")

        try:
            client = get_api_client_config(client_id)
        except ValidationError as exc:
            _audit_auth_failure(client_id=client_id, reason="unknown_client", path=request.path)
            raise AuthenticationFailed("Unknown API client.") from exc

        if not client.enabled:
            _audit_auth_failure(client_id=client_id, reason="disabled_client", path=request.path)
            raise AuthenticationFailed("API client is disabled.")

        api_key = request.headers.get("X-LedgerOS-API-Key", "").strip()
        if api_key:
            if not client.api_key_env:
                _audit_auth_failure(client_id=client_id, reason="api_key_not_configured", path=request.path)
                raise AuthenticationFailed("API key authentication is not enabled for this client.")
            expected = os.getenv(client.api_key_env)
            if not expected or not secrets.compare_digest(api_key, expected):
                _audit_auth_failure(client_id=client_id, reason="invalid_api_key", path=request.path)
                raise AuthenticationFailed("Invalid API key.")
            principal = ApiClientPrincipal(
                client_id=client_id,
                auth_mode="api_key",
                scopes=client.scopes,
                allowed_event_types=client.allowed_event_types,
            )
            return principal, ApiClientAuthContext(
                client_id=client_id,
                auth_mode="api_key",
                nonce="",
                timestamp="",
                request_hash="",
            )

        timestamp = request.headers.get("X-LedgerOS-Timestamp", "").strip()
        nonce = request.headers.get("X-LedgerOS-Nonce", "").strip()
        signature = request.headers.get("X-LedgerOS-Signature", "").strip()
        if not timestamp or not nonce or not signature:
            _audit_auth_failure(client_id=client_id, reason="missing_hmac_headers", path=request.path)
            raise AuthenticationFailed("Missing HMAC authentication headers.")

        _validate_timestamp(timestamp)

        secret = os.getenv(client.secret_env)
        if not secret:
            _audit_auth_failure(client_id=client_id, reason="missing_secret_env", path=request.path)
            raise AuthenticationFailed("API client secret is not configured.")

        body = _canonicalize_body(request)
        expected_signature = hmac.new(
            secret.encode("utf-8"),
            _build_signature_payload(client_id=client_id, method=request.method, path=request.path, timestamp=timestamp, nonce=nonce, body=body),
            hashlib.sha256,
        ).hexdigest()
        if not secrets.compare_digest(signature, expected_signature):
            _audit_auth_failure(client_id=client_id, reason="invalid_signature", path=request.path)
            raise AuthenticationFailed("Invalid API request signature.")

        principal = ApiClientPrincipal(
            client_id=client_id,
            auth_mode="hmac",
            scopes=client.scopes,
            allowed_event_types=client.allowed_event_types,
        )
        return principal, ApiClientAuthContext(
            client_id=client_id,
            auth_mode="hmac",
            nonce=nonce,
            timestamp=timestamp,
            request_hash=hashlib.sha256(body).hexdigest(),
        )
