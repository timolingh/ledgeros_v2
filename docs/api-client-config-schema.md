# API Client Config Schema

This document defines the YAML-managed API client configuration used by Epic 5.

## Purpose

- Keep API client setup versionable and deployment-friendly.
- Avoid storing secrets in committed plaintext files.
- Support read-only visibility in the UI without allowing secret edits there.

## Required Fields

Each client entry must define:

- `client_id`
- `enabled`
- `secret_env`
- `scopes`
- `allowed_event_types`

## Recommended Schema Shape

```yaml
api_clients:
  - client_id: billing_layer
    enabled: true
    secret_env: LEDGEROS_API_CLIENT_BILLING_SECRET
    scopes:
      - invoices
      - payments
    allowed_event_types:
      - invoice.post_requested
      - payment.post_requested
```

## Field Rules

- `client_id` must be unique across configured clients.
- `enabled` must be a boolean.
- `secret_env` must point to an environment variable or equivalent secret reference.
- `scopes` must be explicit and minimal.
- `allowed_event_types` must match the API event vocabulary used by the implementation.
- plaintext secrets must not appear in the YAML file.
- the MVP schema should avoid extra optional fields unless the implementation needs them.

## Validation Expectations

- invalid YAML must fail loudly at load time
- missing required keys must fail validation
- empty scopes should be rejected
- unknown event types should be rejected
- duplicate client IDs should be rejected

## Operational Notes

- The UI may display client status, scopes, and recent failures in read-only mode.
- Secret rotation should be handled by changing the secret reference, not by editing the YAML into a plaintext credential.
- The schema should stay narrow until the implementation proves it needs more fields.
