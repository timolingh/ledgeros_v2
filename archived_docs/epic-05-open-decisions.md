# Epic 5 Decisions

These were the remaining Epic 5 choices and are now resolved.

## 1. Authentication Mechanism

Resolved: HMAC for write endpoints, with limited API keys allowed only where the implementation explicitly defines lower-risk access.

## 2. HTTP Surface Shape

Resolved: hybrid. HTTP paths may be resource-shaped, while payloads remain event-shaped.

## 3. Bank Events in MVP

Resolved: defer bank events to a later step.

## 4. Idempotency Result Contract

Resolved: duplicate submission returns the full original success payload.

## 5. External Invoice Number Ownership

Resolved: unique per client plus entity.

## 6. YAML Client Schema Strictness

Resolved: keep the schema minimal for MVP.
