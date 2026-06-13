# API Auth and Idempotency

This document collects the MVP assumptions that matter most for secure API writes.

## Authentication

The PRD prefers HMAC-signed requests for write endpoints, with scoped API clients managed through config.

Resolved MVP policy:

- HMAC is required for write requests.
- Limited API keys may be used only for explicitly defined low-risk cases.
- Any write path that can post or mutate accounting records must use the HMAC-controlled path.

Whichever approach is chosen, the implementation must:

- authenticate every protected request
- enforce client scopes
- keep secrets out of committed config
- avoid logging secrets in plaintext

## Replay Protection

If HMAC is used, the implementation should validate:

- timestamp skew
- nonce reuse
- signature correctness

Replay protection is especially important for write operations that can post journal entries.

## Idempotency

Every write request must include an idempotency key.

Expected behavior:

- the first accepted request creates the ledger result
- a duplicate request with the same client and idempotency key returns the original result
- a replay must not create duplicate postings
- the original processing status should remain discoverable

## Suggested Storage Behavior

Persist enough information to detect and explain duplicates:

- client ID
- idempotency key
- event type
- request hash or similar fingerprint
- resulting record IDs
- final status

## Edge Cases That Need a Clear Policy

- same idempotency key, different payload
- same idempotency key, different client
- duplicate request after a partial failure
- duplicate request after a successful post but before response delivery
