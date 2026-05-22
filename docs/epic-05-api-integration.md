# Epic 5 — API Ingestion and Config-Managed Integration

## Purpose
Implement the controlled Business Layer Interface and API client configuration required by the MVP.

## In Scope
- Accounting event ingestion API
- API schemas for invoices, payments, credits, refunds, and bank events
- Config-managed API clients
- Idempotency and validation error handling
- External invoice number ownership for API-submitted records
- Stable integration contract for external business layers
- Dockerized API runtime for local development, testing, and deployment

## Why this epic exists
One of the product goals is safe, reliable external integration without owning the business layer. This epic delivers that interface.

## Deliverables
- HTTP API for inbound accounting events
- API request validation and schema enforcement
- API client registration/configuration via YAML
- API key or equivalent config-managed authentication support for MVP
- Idempotent ingestion design
- Error reporting for invalid accounting events
- Audit logs for API-submitted changes

## Implementation Notes
- Implementation must use Django REST Framework for the accounting event ingestion API.
- The API layer must run containerized in Docker, with configuration and secrets injected through environment variables or mounted config.
- Define a minimal API surface, for example:
  - `POST /api/v1/invoices`
  - `POST /api/v1/bills`
  - `POST /api/v1/payments`
  - `POST /api/v1/credits`
  - `POST /api/v1/bank-events`
- Authentication and config:
  - API clients are registered in YAML with client_id, api_key, entity_id, and permitted event types.
  - Example YAML:
    ```yaml
    api_clients:
      - client_id: ledgeros_partner
        api_key: secret-key
        entity_id: default
        scopes:
          - invoices
          - payments
    ```
- Idempotency:
  - Accept an `Idempotency-Key` header or equivalent payload field.
  - Reuse existing ledger records when duplicate events are submitted with the same key.
- Validation rules:
  - reject missing required fields
  - reject unbalanced invoice/bill payloads
  - reject invalid dates, closed periods, or unknown account codes
  - return structured error payloads with field-level details
- API-submitted invoices should preserve `external_invoice_number` while still writing supporting internal numbering if needed.
- Audit logs should record API request metadata, client identity, request payload, and resulting record IDs.

## Example Success Scenarios
- An external business system posts an invoice payload with `external_invoice_number` and receives a 201 with the created invoice ID.
- A duplicate invoice payload with the same `Idempotency-Key` returns the original invoice without creating a second journal entry.
- A payment payload is rejected with a structured error when required fields are missing.
- API client configuration in YAML is loaded and used to validate requests at runtime.

## Acceptance Criteria
- External clients can submit accounting events via the API
- The API rejects invalid or unbalanced accounting payloads with clear errors
- API clients are configured via YAML and can be managed without code changes
- API-submitted invoices preserve external invoice numbers
- API submissions generate the same ledger entries as UI-created accounting records
- API submissions are logged in the audit trail
- The API can be started and validated in Docker containers

## Testing Instructions
- Unit tests for:
  - API schema validation and error responses
  - YAML client configuration loading and permission enforcement
  - idempotency key handling
  - preservation of external invoice numbers
- Integration tests for:
  - full request flow from API event to posted journal entry
  - duplicate submission handling using `Idempotency-Key`
  - invalid payload rejection and correct error detail
  - API request audit logging
- End-to-end tests to compare API-submitted invoice creation with UI-created invoice creation in terms of posted ledger result.

## Dependencies
- Epic 1: Foundational Accounting Core
- Epic 2: AR/AP

## Approval
- Status: **Pending**
- Approval required before any code is built against this epic.
