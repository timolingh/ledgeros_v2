# Epic 5 API Contract

This document captures the stable business contract for Epic 5 without forcing a transport decision too early.

## Contract Goals

- External systems can submit accounting events safely and repeatably.
- Requests are validated before they can affect the ledger.
- Duplicate submissions do not create duplicate postings.
- API-submitted records preserve external references needed for reconciliation and support.
- The same accounting services remain the source of truth.

## Canonical Concepts

- **Client**: a registered external integration with explicit scopes and allowed event types.
- **Event**: a business action submitted by the client, such as posting an invoice or recording a payment.
- **Idempotency key**: client-supplied token used to prevent duplicate processing.
- **External reference**: the foreign system's object identifier and object type.
- **Accounting result**: the created or reused domain record plus any posted journal entry IDs.

## Event Families

The PRD and Epic 5 reference these write event families for the MVP contract:

- invoice posting
- bill posting
- customer payment posting
- vendor payment posting
- credit memo posting
- refund posting

The implementation should keep the business semantics event-centric even if the HTTP paths are resource-oriented.
Resolved transport shape: hybrid. HTTP paths may be resource-shaped while payloads remain event-shaped.
Bank events are deferred from Epic 5 MVP.

## Required Request Data

Every write request must make the following data available either in headers or payload:

- client identity
- idempotency key
- event type
- source system reference
- entity context, if the transport allows it
- event payload

Every business payload must support the accounting fields needed to validate the record before posting.

For MVP, the accounting module uses the hidden default entity, so external requests do not need to provide `entity_id`.
Duplicate requests must return the full original success payload, not a reduced duplicate envelope.

## Validation Rules

- required fields must be present
- unknown account, customer, or vendor references must be rejected
- invalid dates must be rejected
- closed-period writes must be rejected
- unbalanced invoice or bill data must be rejected
- unauthorized scopes must be rejected
- duplicate idempotency keys must return the original result

## Response Expectations

Successful requests should return:

- the created or reused domain record identifier
- the posted journal entry identifier, if one was created
- the final processing status
- the external reference that was stored

Rejected requests should return:

- a stable error code
- human-readable detail
- field-level errors where applicable

## Audit Expectations

Audit data for API submissions should preserve:

- client identity
- request timestamp
- request type
- processed record identifiers
- validation or authentication failures
- non-secret request metadata

Secrets, authorization headers, and replay material must not be logged in plaintext.
