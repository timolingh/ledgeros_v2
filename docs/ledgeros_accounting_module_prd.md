# PRD — LedgerOS Accounting Module

## Standardized Accounting Core with Controlled Business Layer Interface

---

# 1. Product Overview

## 1.1 Product Name

**LedgerOS Accounting Module**

## 1.2 Product Description

LedgerOS Accounting Module is a modular accounting system that serves as the authoritative financial system of record.

It provides core accounting capabilities including:

- general ledger
- chart of accounts
- accounts receivable
- accounts payable
- banking and reconciliation
- financial reporting
- tax accounting support
- permissions
- audit logs
- accounting event ingestion APIs
- browser-based accounting UI

The product is intentionally limited to accounting functionality.

It is not a business application, workflow builder, CRM, ERP, customer portal, project management tool, or industry-specific operating system.

The only supported relationship to external business functionality is through a controlled **Business Layer Interface**, where an external business layer may submit accounting-relevant events to the accounting module.

The accounting module must also be usable without any connected business layer through a browser-based **Core Accounting UI**.

---

# 2. Product Goals

The goal is to build a reliable, auditable, platform-agnostic, API-accessible accounting module that can:

1. maintain balanced books
2. enforce accounting controls
3. support core SMB accounting workflows
4. support both cash-basis and accrual-basis reporting
5. integrate with external business layers through defined accounting APIs
6. preserve immutable audit history
7. support self-hosted deployment
8. avoid dependency on any specific desktop operating system
9. provide a browser-based UI for direct accounting use
10. provide enough structure that implementation can be decomposed into clear engineering tasks

---

# 3. Product Non-Goals

LedgerOS Accounting Module will not provide:

- business workflow builders
- operational workflow management
- CRM functionality
- project management
- field service workflows
- property management workflows
- construction workflows
- logistics workflows
- medical billing workflows
- legal case workflows
- customer-facing business portals
- custom form builders
- non-accounting approval routing
- industry-specific business applications
- business process automation outside accounting
- ERP-wide operational modules
- unrestricted direct production database access for reporting
- multi-entity accounting in MVP
- consolidated reporting in MVP
- intercompany transactions in MVP
- managed hosting in MVP
- multi-currency in MVP
- OAuth API client authentication in MVP

The module may receive accounting events from an external business layer, but it must not own or implement that business layer.

---

# 4. Target Users and Personas

## 4.1 Primary Users

| Persona | Description | Primary Needs |
|---|---|---|
| Controller | Owns accounting accuracy and financial reporting | close periods, review books, generate financial statements |
| Bookkeeper | Performs day-to-day accounting work | enter transactions, reconcile accounts, manage AR/AP |
| Staff Accountant | Handles journals, adjustments, reports | post entries, review ledgers, resolve exceptions |
| External Accountant / CPA | Reviews and adjusts books | audit trail, reports, journal entries, exports |
| Accounting Admin | Configures system and permissions | users, roles, chart of accounts, accounting periods |
| Integration Developer | Connects external business layer to accounting module | stable APIs, schemas, validation errors, idempotency |

## 4.2 Buyers / Decision Makers

| Buyer | Motivation |
|---|---|
| SMB owner | Wants control, reliability, and lower platform dependency |
| CFO / Controller | Wants trustworthy books and auditability |
| Software vendor | Wants embedded accounting capabilities through APIs |
| Managed service provider | Wants deployable accounting infrastructure |

---

# 5. Problem Statement

SMBs and software platforms need a modern accounting system of record that is reliable, auditable, platform-agnostic, and integration-friendly.

Existing options often create one or more of the following problems:

- accounting data is locked inside closed platforms
- API access is limited or inconsistent
- self-hosting is unavailable
- desktop products are tied to a specific operating system
- audit trails are incomplete or hard to inspect
- external systems cannot safely create accounting transactions
- accounting behavior is mixed with operational business workflows
- implementation boundaries are unclear
- advanced users cannot reliably access accounting data without risking report inconsistency
- users cannot operate the accounting core directly without a business application layer
- setup of large charts of accounts through UI-only workflows is tedious and hard to version-control

LedgerOS Accounting Module solves this by providing a focused accounting core with:

- explicit accounting APIs
- browser-based accounting UI
- platform-agnostic access
- clear system boundaries
- enforceable accounting controls
- implementation-ready requirements
- CSV import/export
- YAML-based version-manageable configuration for selected setup objects

---

# 6. Scope

## 6.1 In Scope

The product includes:

- chart of accounts
- general ledger
- journal entries
- accounting periods
- period locking
- accounts receivable
- accounts payable
- customer accounting records
- vendor accounting records
- invoice accounting records
- bill accounting records
- internally generated invoice numbers for UI-created invoices
- externally supplied invoice numbers for externally submitted invoices
- payments
- credits
- refunds
- banking
- bank reconciliation
- financial reporting
- configurable standard reports
- saved report views
- report drill-down
- report APIs
- cash-basis and accrual-basis reporting
- US and California tax accounting support for MVP
- permissions
- audit logs
- browser-based Core Accounting UI
- accounting event ingestion
- accounting APIs
- CSV import/export
- YAML chart of accounts configuration
- YAML API client configuration
- platform-agnostic deployment tooling
- PostgreSQL production database

## 6.2 Out of Scope

The product excludes:

- business workflow design
- operational workflow design
- business-specific approvals outside accounting
- industry-specific modules
- CRM
- ERP operations
- customer portals
- job management
- inventory operations, unless later defined only as accounting inventory valuation
- payroll processing
- non-accounting document management
- non-accounting task management
- arbitrary SQL report builder in MVP
- unrestricted direct access to production database tables
- direct reporting against mutable production tables
- multi-entity UX, APIs, reporting, or consolidation in MVP
- external API auto-creation of customers/vendors in MVP
- managed hosting in MVP
- OAuth in MVP
- JSON configuration requirement in MVP
- Markdown as authoritative machine-readable configuration

---

# 7. MVP Definition

The MVP must deliver a usable accounting module with a narrow but complete accounting loop.

## 7.1 MVP Modules

| Module | MVP Status |
|---|---|
| Browser-based Core Accounting UI | Required |
| General Ledger | Required |
| Chart of Accounts | Required |
| Journal Entries | Required |
| Accounting Periods | Required |
| Period Locking | Required |
| Accounts Receivable | Required |
| Accounts Payable | Required |
| Basic Banking | Required |
| Bank Reconciliation | Required |
| Financial Reporting | Required |
| Cash/Accrual Report Basis Support | Required |
| Report Builder Lite | Required |
| Permissions | Required |
| Audit Logs | Required |
| Accounting Event API | Required |
| Config-managed API Clients | Required |
| CSV Import/Export | Required |
| YAML Chart of Accounts Configuration | Required |
| Platform-Agnostic Deployment | Required |
| PostgreSQL Production Database | Required |
| Tax | US and California MVP support |
| Multi-Entity | Post-MVP |
| Multi-Currency | Post-MVP |
| Managed Hosting | Post-MVP |

## 7.2 MVP Entity Assumption

The MVP is single-entity from the user’s perspective.

Each company/workspace automatically receives one internal hidden default entity.

All MVP transactions, accounts, reports, periods, customers, vendors, invoices, bills, payments, bank accounts, and audit logs belong to that hidden default entity.

The MVP data model should not require users to configure multiple entities before using the system.

The UI must not expose entity selectors, entity management screens, entity-level report filters, consolidation, or intercompany behavior in MVP.

The API must not require `entity_id` in MVP. If omitted, the system assigns the workspace’s hidden default entity. If supplied, the system should reject it unless it matches the hidden default entity.

## 7.3 Deferred Until Post-MVP

| Feature | Reason Deferred |
|---|---|
| multi-entity accounting | not required for first usable accounting loop |
| entity-level reporting | depends on multi-entity support |
| consolidated reports | depends on multi-entity support |
| intercompany transactions | complex accounting behavior |
| intercompany eliminations | complex accounting behavior |
| multi-currency | affects ledger, reporting, reconciliation, and FX handling |
| automated bank feeds | integration complexity |
| ACH/check run automation | payment rail complexity |
| advanced VAT/GST handling | jurisdiction complexity |
| advanced 1099 workflows | year-end compliance complexity |
| fully custom report builder | not required for MVP |
| arbitrary SQL report builder | risk to accounting correctness and supportability |
| controlled SQL analytics layer | useful, but should use stable read-only reporting views post-MVP |
| advanced approval chains | risk of becoming workflow platform |
| inventory costing | requires separate accounting policy definition |
| payroll accounting | requires separate compliance scope |
| native desktop applications | optional clients only; not required for core functionality |
| managed hosting | self-hosted/container deployment is MVP |
| OAuth 2.0 client credentials | more complex than needed for MVP server-to-server integrations |

---

# 8. Product Principles

## 8.1 Accounting Integrity Is Sacred

The system must never create invalid books.

The accounting module must enforce:

- balanced journal entries
- valid accounting periods
- immutable posted records where required
- audit history
- permission checks
- referential integrity
- idempotent API posting
- deterministic ledger outcomes

## 8.2 Accounting Module Owns Accounting Records

The accounting module owns accounting records and accounting state.

External systems may reference those records, but may not bypass accounting controls.

## 8.3 External Business Layers Are Integration Clients Only

External business layers may submit accounting events.

The accounting module validates those events and decides whether to create accounting records.

## 8.4 Native Accounting Usability

The accounting module must be usable without an external business layer.

A user must be able to configure the accounting system, enter accounting transactions, reconcile accounts, generate reports, and review audit history directly through the Core Accounting UI.

## 8.5 Platform Agnosticism

LedgerOS Accounting Module must be platform-agnostic.

The product must not require users to run a specific desktop operating system such as Windows, macOS, or Linux.

The primary user interface should be browser-based.

The server-side application should support containerized deployment and should be deployable on common Linux-based infrastructure and self-hosted environments.

Native desktop applications, if ever created, are optional clients and must not be required for core accounting functionality.

## 8.6 Configuration Without Bypassing Validation

The system should support text-based configuration where it improves repeatability, version control, and deployment.

Text-based configuration must not bypass accounting services, validation, permissions, or audit logging.

CSV is used for import/export.

YAML is used for declarative configuration of selected setup objects, including chart of accounts and API clients.

## 8.7 Implementation Must Be Explicit and Testable

Each requirement should be capable of becoming:

- a ticket
- a database migration
- an API endpoint
- a service method
- a permission rule
- an automated test
- a user acceptance test

---

# 9. System Boundary

## 9.1 Boundary Summary

```txt
Browser-Based Core Accounting UI
        ↓
Accounting Services + APIs
        ↓
Validation + Permission Checks
        ↓
Posting Engine
        ↓
General Ledger
        ↓
Reports + Audit Logs
```

```txt
External Business Layer
        ↓
Accounting Event API
        ↓
Validation + Permission Checks
        ↓
Accounting Services
        ↓
Posting Engine
        ↓
General Ledger
        ↓
Reports + Audit Logs
```

## 9.2 Boundary Rules

The Core Accounting UI may:

- configure accounting settings
- create accounting records
- submit accounting actions to accounting services
- generate reports
- manage users and permissions
- review audit logs
- inspect accounting event status

The external business layer may:

- submit accounting events
- reference external object IDs
- provide invoice numbers for externally submitted invoices
- receive accounting status responses
- query authorized accounting records
- receive webhooks for accounting status changes, post-MVP

The external business layer may not:

- write directly to ledger tables
- create unbalanced journal entries
- mutate posted accounting records
- post into locked periods
- suppress audit logs
- bypass permissions
- delete accounting history
- define non-accounting workflows inside the accounting module
- automatically create customer/vendor records in MVP

---

# 10. Core Accounting UI

## 10.1 Purpose

The MVP includes a browser-based Core Accounting UI.

The Core Accounting UI is the primary way users interact with the accounting module when no external business layer is connected.

The UI is a client of the same accounting services and APIs used by integrations.

The Core Accounting UI is limited to accounting-native workflows and must not include business workflow, CRM, ERP, project management, industry-specific, or operational application features.

## 10.2 Core Accounting UI Areas

| Area | MVP Screens |
|---|---|
| Setup | company/workspace settings, accounting basis setting, fiscal year settings, chart of accounts, tax codes, accounting periods, users, roles, customers, vendors, bank accounts |
| General Ledger | account list, account detail, journal entry list, journal entry editor, posting, reversal, ledger detail |
| Accounts Receivable | customer list, customer detail, invoice list, invoice editor, invoice numbering, payment entry, credit memo, invoice void, AR aging |
| Accounts Payable | vendor list, vendor detail, bill list, bill editor, vendor payment, vendor credit, bill void, AP aging |
| Banking | bank account list, bank account detail, CSV import, transaction matching, manual transaction entry, reconciliation workspace |
| Reporting | report library, configurable reports, cash/accrual basis selector where supported, saved report views, drill-down, CSV export |
| Audit & Controls | audit log, period close/lock controls, accounting event log, failed event queue |
| Integration Console | configured API client status, scopes, allowed event types, event status, validation errors, idempotency lookup, auth failure visibility |

## 10.3 Core Accounting UI Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| UI-001 | Provide browser-based accounting UI | MVP | User can access core accounting workflows through a modern browser |
| UI-002 | Use accounting services as backend | MVP | UI actions call the same accounting services used by APIs |
| UI-003 | Provide setup workflow | MVP | User can configure company settings, accounting basis, chart of accounts, periods, tax codes, users, customers, vendors, and bank accounts |
| UI-004 | Provide GL workflow | MVP | User can create, post, view, and reverse journal entries |
| UI-005 | Provide AR workflow | MVP | User can create invoices, post invoices, record payments, issue credits, and view AR aging |
| UI-006 | Provide AP workflow | MVP | User can create bills, post bills, record vendor payments, apply credits, and view AP aging |
| UI-007 | Provide banking workflow | MVP | User can import, match, manually enter, and reconcile bank transactions |
| UI-008 | Provide reporting workflow | MVP | User can generate, configure, save, drill into, and export accounting reports |
| UI-009 | Provide audit/control workflow | MVP | User can view audit logs, period controls, and accounting event history |
| UI-010 | Preserve accounting-only scope | MVP | UI does not include CRM, project management, operational workflow, or industry-specific business features |
| UI-011 | Support customer/vendor pre-setup | MVP | User can create or CSV-import customers/vendors before submitting external events |
| UI-012 | Display failed customer/vendor reference errors | MVP | Integration Console shows unknown customer/vendor errors with actionable messages |
| UI-013 | Show read-only API client status | MVP | Integration Console displays configured API clients, scopes, allowed event types, status, and recent failures without editing secrets |

---

# 11. Object Ownership Matrix

| Object | System of Record | External Reference Allowed | Notes |
|---|---|---:|---|
| Company / Workspace | Accounting Module | Optional | MVP company context |
| Hidden Default Entity | Accounting Module | No | Internal only for future multi-entity compatibility |
| Account | Accounting Module | No | Chart of accounts owned by accounting |
| JournalEntry | Accounting Module | Yes | May originate from API event |
| JournalLine | Accounting Module | No | Created only by posting engine |
| CustomerAccountingRecord | Accounting Module | Yes | May reference external customer ID, but must be created explicitly before external use |
| VendorAccountingRecord | Accounting Module | Yes | May reference external vendor ID, but must be created explicitly before external use |
| InvoiceAccountingRecord | Accounting Module | Yes | Accounting representation of invoice |
| InvoiceNumber | Accounting Module or External Layer | Yes | UI-created invoices may use internal numbering; external invoices preserve supplied number |
| BillAccountingRecord | Accounting Module | Yes | Accounting representation of vendor bill |
| Payment | Accounting Module | Yes | Accounting payment record |
| CreditMemo | Accounting Module | Yes | Accounting credit record |
| BankAccount | Accounting Module | No | Accounting-owned financial account |
| BankTransaction | Accounting Module | Optional | May come from import/feed |
| AccountingPeriod | Accounting Module | No | Controls posting rules |
| ReportView | Accounting Module | No | Saved configuration for standard accounting report |
| AuditLog | Accounting Module | No | Immutable accounting history |
| AccountingEvent | Accounting Module | Yes | Stores source event and result |
| APIClientConfig | Deployment Config | No | YAML-managed in MVP; status visible in Integration Console |
| Business Object | External Business Layer | N/A | Not owned or modeled except by reference |

---

# 12. Core Data Model

## 12.1 Core Entities

| Entity | Description |
|---|---|
| CompanyWorkspace | MVP company/workspace context |
| HiddenDefaultEntity | Internal entity for future multi-entity compatibility |
| Account | Chart of accounts entry |
| JournalEntry | Header for accounting transaction |
| JournalLine | Debit or credit line |
| AccountingPeriod | Open, soft-closed, locked, or reopened period |
| CustomerAccountingRecord | Customer record for accounting use |
| VendorAccountingRecord | Vendor record for accounting use |
| InvoiceAccountingRecord | AR invoice accounting record |
| InvoiceLine | Invoice accounting line |
| InvoiceNumberSequence | Internal numbering rule for UI-created invoices |
| Payment | Customer or vendor payment |
| PaymentApplication | Application of payment to invoice or bill |
| CreditMemo | Customer credit |
| BillAccountingRecord | AP bill accounting record |
| BillLine | Bill accounting line |
| VendorPayment | Payment to vendor |
| BankAccount | Bank or cash account |
| BankTransaction | Imported or manually entered bank transaction |
| Reconciliation | Bank reconciliation record |
| TaxCode | Tax accounting configuration |
| TaxJurisdiction | Tax jurisdiction metadata |
| ReportView | Saved configuration for a standard accounting report |
| User | System user |
| Role | Permission grouping |
| Permission | Specific allowed action |
| AuditLog | Immutable event history |
| AccountingEvent | External or internal event submitted for posting |

## 12.2 Required Relationships

```txt
CompanyWorkspace
  → has one HiddenDefaultEntity
  → has many Accounts
  → has many AccountingPeriods
  → has many JournalEntries
  → has many Users
  → has many BankAccounts
  → has accounting_basis setting: cash or accrual

HiddenDefaultEntity
  → belongs to CompanyWorkspace
  → is assigned automatically to MVP accounting records

JournalEntry
  → has many JournalLines
  → belongs to CompanyWorkspace
  → belongs to HiddenDefaultEntity
  → belongs to AccountingPeriod
  → may reference AccountingEvent

InvoiceAccountingRecord
  → has many InvoiceLines
  → has invoice_number
  → may have external_invoice_number/source reference
  → may create one or more JournalEntries
  → may receive Payments through PaymentApplications
  → may be credited by CreditMemo

BillAccountingRecord
  → has many BillLines
  → may create one or more JournalEntries
  → may be paid by VendorPayment through PaymentApplications

Payment
  → has payment_date
  → may have many PaymentApplications
  → supports cash-basis reporting allocation

AccountingEvent
  → may create InvoiceAccountingRecord, Payment, BillAccountingRecord, Expense, or JournalEntry
  → must store idempotency key
  → must store validation status
  → must store posting result
  → may store external invoice number
  → must reject unknown customer/vendor references

ReportView
  → belongs to User
  → references base ReportType
  → stores filters, basis selection where supported, grouping, visible columns, and sort order
```

---

# 13. Lifecycle States

## 13.1 Journal Entry Lifecycle

```txt
draft → posted → reversed
```

Rules:

- draft journal entries may be edited
- posted journal entries may not be destructively edited
- posted journal entries may be reversed
- reversal creates a new journal entry
- original journal entry remains visible and unchanged

## 13.2 Invoice Lifecycle

```txt
draft → posted → partially_paid → paid
              ↘ voided
              ↘ credited
```

Rules:

- draft invoices may be edited
- posted invoices may not be destructively edited
- posted invoices create ledger impact
- voiding a posted invoice requires reversal entries
- payments may not be applied to voided invoices
- partial payments reduce open balance
- overpayments create unapplied customer credit
- UI-created invoices may use internal invoice number generation
- externally submitted invoices preserve externally supplied invoice numbers

## 13.3 Bill Lifecycle

```txt
draft → posted → partially_paid → paid
              ↘ voided
              ↘ credited
```

Rules:

- draft bills may be edited
- posted bills create ledger impact
- posted bills may not be destructively edited
- vendor credits reduce payable balance
- payments may not be applied to voided bills

## 13.4 Accounting Period Lifecycle

```txt
open → soft_closed → locked → reopened
```

Rules:

- open periods accept valid postings
- soft-closed periods require elevated permission
- locked periods reject postings
- reopened periods require permission and reason
- all reopen actions must create audit logs

## 13.5 Accounting Event Lifecycle

```txt
received → validating → rejected
                    ↘ posted
                    ↘ failed
                    ↘ duplicate_returned
```

Rules:

- every submitted event receives a durable event record
- duplicate idempotency keys must not create duplicate postings
- rejected events do not create accounting records
- failed events must preserve error details
- posted events must reference created accounting records
- unknown customer/vendor references are rejected
- external events may not implicitly create customers or vendors

---

# 14. Functional Requirements

## 14.1 General Ledger

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| GL-001 | Create chart of accounts | MVP | Authorized user can create account with valid type, code, and name |
| GL-002 | Edit chart of accounts | MVP | Authorized user can edit non-posting metadata; system prevents edits that would corrupt history |
| GL-003 | Create draft journal entry | MVP | Authorized user can create draft entry with one or more lines |
| GL-004 | Post balanced journal entry | MVP | System posts only if total debits equal total credits |
| GL-005 | Reject unbalanced journal entry | MVP | System rejects posting and creates no ledger impact |
| GL-006 | Reverse posted journal entry | MVP | System creates reversing entry and preserves original |
| GL-007 | View general ledger detail | MVP | User can filter by account, date range, and status |
| GL-008 | Prevent destructive edits to posted entries | MVP | Posted entries cannot be changed except through reversal or adjustment |
| GL-009 | Enforce accounting periods | MVP | Posting date must belong to an open or permitted soft-closed period |

## 14.2 Accounting Periods

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| PERIOD-001 | Create accounting period | MVP | Authorized user can create non-overlapping period |
| PERIOD-002 | Soft close period | MVP | Soft-closed period requires elevated permission for posting |
| PERIOD-003 | Lock period | MVP | Locked period rejects all postings unless reopened |
| PERIOD-004 | Reopen period | MVP | Authorized user can reopen period with required reason |
| PERIOD-005 | Audit period changes | MVP | Every close, lock, and reopen action is logged |

## 14.3 Accounts Receivable

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| AR-001 | Create customer accounting record | MVP | Authorized user, CSV import, or explicit customer API may create customer accounting record |
| AR-002 | Create draft invoice | MVP | Draft invoice creates no ledger impact |
| AR-003 | Post invoice | MVP | Posting creates balanced journal entry debiting AR and crediting revenue/tax liability |
| AR-004 | Record customer payment | MVP | Payment reduces invoice balance and creates ledger impact |
| AR-005 | Support partial payment | MVP | Invoice status becomes partially paid with correct remaining balance |
| AR-006 | Support overpayment | MVP | Excess amount becomes unapplied customer credit |
| AR-007 | Issue credit memo | MVP | Credit memo reduces customer balance and posts to ledger |
| AR-008 | Void posted invoice | MVP | System creates reversal entry and preserves original invoice |
| AR-009 | Generate AR aging | MVP | Report shows open receivables by aging bucket |
| AR-010 | Generate invoice numbers for UI-created invoices | MVP | When a user creates an invoice in the Core Accounting UI, the system can generate a unique invoice number using workspace numbering rules |
| AR-011 | Preserve externally supplied invoice numbers | MVP | When an invoice is submitted by external event, the system stores the external invoice number without replacing it |
| AR-012 | Separate invoice number from external reference | MVP | Invoice number and external object reference are stored as distinct fields |

## 14.4 Accounts Payable

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| AP-001 | Create vendor accounting record | MVP | Authorized user, CSV import, or explicit vendor API may create vendor accounting record |
| AP-002 | Create draft bill | MVP | Draft bill creates no ledger impact |
| AP-003 | Post bill | MVP | Posting creates balanced journal entry crediting AP and debiting expense/asset/tax accounts |
| AP-004 | Record vendor payment | MVP | Payment reduces bill balance and creates ledger impact |
| AP-005 | Support partial vendor payment | MVP | Bill status becomes partially paid with correct remaining balance |
| AP-006 | Apply vendor credit | MVP | Vendor credit reduces payable balance |
| AP-007 | Void posted bill | MVP | System creates reversal entry and preserves original bill |
| AP-008 | Generate AP aging | MVP | Report shows open payables by aging bucket |

## 14.5 Banking and Reconciliation

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| BANK-001 | Create bank account | MVP | Authorized user can create bank account linked to GL account |
| BANK-002 | Import bank transactions via CSV | MVP | System imports valid CSV rows and rejects invalid rows with errors |
| BANK-003 | Match bank transaction | MVP | User can match bank transaction to accounting transaction |
| BANK-004 | Create manual bank transaction | MVP | Authorized user can create transaction with ledger impact |
| BANK-005 | Reconcile bank account | MVP | User can reconcile statement balance to book balance |
| BANK-006 | Store reconciliation report | MVP | Completed reconciliation creates immutable record |
| BANK-007 | Prevent reconciliation mismatch | MVP | System does not complete reconciliation if unresolved difference exists |

## 14.6 Financial Reporting

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| REPORT-001 | Generate trial balance | MVP | Total debits equal total credits |
| REPORT-002 | Generate balance sheet | MVP | Assets equal liabilities plus equity |
| REPORT-003 | Generate profit and loss statement | MVP | Report includes income and expense accounts for period |
| REPORT-004 | Generate general ledger report | MVP | Report shows transactions by account and date |
| REPORT-005 | Generate AR aging report | MVP | Report matches unpaid AR balances |
| REPORT-006 | Generate AP aging report | MVP | Report matches unpaid AP balances |
| REPORT-007 | Export reports | MVP | User can export reports to CSV |
| REPORT-008 | Provide configurable standard reports | MVP | User can open a standard report and configure supported filters |
| REPORT-009 | Support predefined grouping | MVP | User can group supported reports by account, account type, customer, vendor, period, source type, or tax code where applicable |
| REPORT-010 | Support drill-down | MVP | User can click a report amount and view supporting accounting transactions |
| REPORT-011 | Save report view | MVP | User can save report configuration with filters, columns, grouping, basis where supported, and sort order |
| REPORT-012 | Load saved report view | MVP | User can reopen saved report view and regenerate current results |
| REPORT-013 | Export configured report | MVP | User can export the currently configured report to CSV |
| REPORT-014 | Restrict reports to accounting data | MVP | Report builder cannot query or display non-accounting business-layer data |
| REPORT-015 | Prevent raw production database reporting dependency | MVP | MVP reporting does not require users to query internal production tables directly |
| REPORT-016 | Provide accounting-approved report data model | MVP | Standard reports are generated from posted accounting records and respect permission, period, and reversal rules |
| REPORT-017 | Provide report API access | MVP | Authorized users or clients can retrieve supported report outputs through stable APIs |
| REPORT-018 | Defer direct SQL analytics to controlled layer | Post-MVP | Advanced SQL access, if provided, uses read-only reporting views or an analytics replica, not mutable production tables |

## 14.7 Cash and Accrual Basis Support

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| BASIS-001 | Configure workspace accounting basis | MVP | Admin can set default basis to cash or accrual |
| BASIS-002 | Label reports by basis | MVP | Supported reports clearly show cash or accrual basis |
| BASIS-003 | Support report-level basis override | MVP | Authorized user can run supported reports using cash or accrual basis |
| BASIS-004 | Preserve source transaction dates | MVP | System stores invoice/bill dates, posting dates, due dates, and payment dates needed for both bases |
| BASIS-005 | Preserve settlement relationships | MVP | System stores payment application relationships needed for cash-basis reporting |
| BASIS-006 | Prevent unsupported basis behavior | MVP | Reports that do not support basis override clearly indicate why |
| BASIS-007 | Support cash-basis P&L | MVP | P&L can recognize income and expenses based on payment activity where applicable |
| BASIS-008 | Support accrual-basis P&L | MVP | P&L can recognize income and expenses based on invoice/bill posting activity |
| BASIS-009 | Use proportional allocation for partial payments | MVP | Cash-basis reporting allocates partial payments proportionally across invoice/bill lines unless later reconfigured |

Rules:

- Trial balance remains ledger-based.
- AR/AP aging remains open-balance tracking, not cash-basis income or expense recognition.
- Cash-basis balance sheet is limited or post-MVP unless explicitly included later.
- Reports must clearly show their basis.

## 14.8 Tax Accounting

MVP tax support is limited to United States and California use cases.

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| TAX-001 | Create tax code | MVP | Authorized user can create tax code with rate and liability account |
| TAX-002 | Apply tax code to invoice line | MVP | Tax amount is calculated and posted to tax liability account |
| TAX-003 | Generate tax liability report | MVP | Report shows tax collected by tax code and period |
| TAX-004 | Support tax-exempt invoice line | MVP | Tax-exempt lines do not generate tax liability |
| TAX-005 | Support US/California MVP tax scope | MVP | Tax configuration supports MVP use cases for United States and California sales tax accounting |
| TAX-006 | Export tax report | Post-MVP | User can export tax details by jurisdiction |

## 14.9 Multi-Entity

Multi-entity support is out of scope for MVP, but the internal schema includes a hidden default entity.

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| ENTITY-000 | Create hidden default entity | MVP | Each workspace automatically receives one internal default entity |
| ENTITY-001-MVP | Assign records to default entity | MVP | All MVP accounting records are automatically associated with the workspace’s default entity |
| ENTITY-002-MVP | Hide multi-entity UX | MVP | Users cannot create, select, filter, consolidate, or manage multiple entities |
| ENTITY-003-MVP | Omit entity from MVP API contract | MVP | MVP API requests do not require external clients to provide `entity_id` |
| ENTITY-004-MVP | Preserve future multi-entity path | MVP | Schema supports future entity-level filtering without requiring a full historical migration |
| ENTITY-001 | Create multiple entities | Post-MVP | Authorized user can create more than one accounting entity |
| ENTITY-002 | Separate books by entity | Post-MVP | Transactions belong to a specific entity |
| ENTITY-003 | Generate entity-level reports | Post-MVP | Reports can be filtered by entity |
| ENTITY-004 | Prevent cross-entity imbalance | Post-MVP | Journal entry must balance within entity unless intercompany feature enabled |
| ENTITY-005 | Consolidated reports | Post-MVP | System can produce consolidated statements |
| ENTITY-006 | Intercompany transactions | Post-MVP | System supports due-to/due-from entries |

## 14.10 Permissions and Audit

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| PERM-001 | Create roles | MVP | Admin can create role with permissions |
| PERM-002 | Assign roles to users | MVP | Admin can assign role to user |
| PERM-003 | Enforce permissions in UI | MVP | Unauthorized UI actions are blocked |
| PERM-004 | Enforce permissions in API | MVP | Unauthorized API actions are rejected |
| AUDIT-001 | Log accounting changes | MVP | All material accounting actions create audit log |
| AUDIT-002 | Preserve actor and timestamp | MVP | Audit log records user/system, timestamp, action, and object |
| AUDIT-003 | Preserve before/after values | MVP | Material edits include before/after data where applicable |
| AUDIT-004 | Make audit logs immutable | MVP | Audit logs cannot be edited or deleted by normal users |

---

# 15. Advanced MVP Reporting

## 15.1 Reporting Philosophy

Advanced users generate reports through configurable standard accounting reports, not a full custom report builder.

The MVP must support practical accounting flexibility while preserving accounting correctness, report consistency, and implementation clarity.

The MVP must not include:

- arbitrary SQL reporting
- drag-and-drop report design
- custom formulas
- embedded BI dashboards
- non-accounting operational reporting
- reporting directly against external business-layer data
- unrestricted direct production database access

## 15.2 Report Builder Lite Capabilities

Advanced users may:

- select from predefined accounting report templates
- apply report-specific filters
- select cash or accrual basis where supported
- group and subtotal by predefined accounting dimensions
- choose visible columns where supported
- sort report rows
- drill down from summary amounts to supporting accounting detail
- save configured report views
- export report results to CSV
- retrieve supported report outputs through stable report APIs

## 15.3 MVP Report Library

| Report | MVP |
|---|---:|
| Trial Balance | Yes |
| Balance Sheet | Yes |
| Profit & Loss | Yes |
| General Ledger Detail | Yes |
| AR Aging | Yes |
| AP Aging | Yes |
| Tax Liability | Yes |
| Transaction Detail by Account | Yes |
| Journal Entry Detail | Yes |

## 15.4 Supported Filters

| Filter | Applies To |
|---|---|
| date range / as-of date | all reports |
| accounting period | all reports |
| basis: workspace default / cash / accrual | supported financial reports |
| account / account range | trial balance, GL detail, transaction detail |
| account type | trial balance, GL detail, P&L, balance sheet |
| customer | AR, invoice/payment reports |
| vendor | AP, bill/payment reports |
| posting status | detail reports |
| source type | GL detail, journal detail |
| tax code | tax reports |
| created by / posted by | audit-style detail reports |

## 15.5 Supported Grouping

| Grouping | Applies To |
|---|---|
| account | GL detail, trial balance |
| account type | trial balance, P&L, balance sheet |
| customer | AR reports |
| vendor | AP reports |
| tax code | tax reports |
| accounting period | P&L, GL detail |
| source type | transaction detail |

## 15.6 Database Access Policy

The MVP must not require or encourage unrestricted direct database access for report generation.

Advanced reporting must be provided through:

- standard accounting reports
- configurable report filters
- saved report views
- drill-down
- report exports
- reporting APIs

The internal production schema is not a public reporting contract.

Reports must be generated from accounting-approved data models that respect:

- posting status
- reversals
- permissions
- accounting period rules
- posted ledger impact
- cash/accrual basis rules where supported

Post-MVP may support controlled read-only SQL access through documented accounting views, a read replica, or an analytics data mart.

---

# 16. Configuration Management

## 16.1 Deployment Configuration

Deployment and infrastructure settings should be manageable through text-based configuration.

Supported MVP configuration mechanisms:

- environment variables
- `.env` files for local/self-hosted development
- YAML configuration files
- Docker-compatible configuration
- documented example config files

Deployment configuration may include:

- database connection references
- public application URL
- logging settings
- storage settings
- email provider settings
- authentication provider settings
- feature flags
- backup settings
- integration endpoint settings
- API client configuration references

Secrets must not be stored in plaintext committed configuration files. Secrets should be supplied through environment variables, local secret files excluded from version control, or secret manager references.

## 16.2 Accounting Configuration

Accounting configuration should be manageable through both:

1. Core Accounting UI/API workflows
2. validated file-based configuration workflows for selected accounting setup objects

The product must not require users to manually edit text files, but advanced users must be able to use text files for repeatable, version-controlled setup where appropriate.

For MVP, file-based accounting configuration is required for chart of accounts.

## 16.3 Chart of Accounts Configuration

The MVP must support:

- CSV import/export for chart of accounts
- YAML declarative configuration for chart of accounts

CSV is intended for accountant-friendly import/export and spreadsheet workflows.

YAML is intended for version-controlled setup, review, and repeatable deployment.

Both formats must be validated before application, and all applied changes must go through accounting services, permissions, and audit logging.

Markdown is not an authoritative configuration format.

JSON is not required for MVP configuration.

## 16.4 Chart of Accounts Apply Workflow

```txt
Upload or reference config file
        ↓
Parse file
        ↓
Validate schema
        ↓
Validate accounting rules
        ↓
Generate preview/diff
        ↓
User approves apply
        ↓
Apply through accounting services
        ↓
Create audit log
        ↓
Return success/errors
```

## 16.5 Chart of Accounts Import Modes

| Mode | Behavior | MVP |
|---|---|---:|
| dry-run | Validates and previews changes without applying | Yes |
| create-only | Adds new accounts; rejects updates to existing accounts | Yes |
| update-metadata | Updates safe metadata such as name, description, inactive flag | Yes |
| replace-draft-setup | Replaces chart only before posted transactions exist | Yes |
| deactivate-missing | Deactivates missing accounts | Post-MVP |

## 16.6 API Client Configuration

API clients are managed through YAML config in MVP.

The Core Accounting UI may show read-only API client status, but must not edit API clients or secrets in MVP.

API client secrets must be referenced through environment variables or secret manager references.

Example:

```yaml
api_clients:
  - client_id: billing_layer
    display_name: External Billing Layer
    enabled: true
    auth_method: hmac_sha256
    secret_env: LEDGEROS_API_CLIENT_BILLING_SECRET
    scopes:
      - accounting_events.submit
      - accounting_events.read
      - reports.read
    allowed_event_types:
      - invoice.post_requested
      - payment.record_requested
    rate_limit_per_minute: 120
```

## 16.7 Configuration Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| CONFIG-001 | Support text-based deployment config | MVP | App can be configured through env vars and documented text config files |
| CONFIG-002 | Provide example deployment config | MVP | Repository includes example `.env` and YAML config templates |
| CONFIG-003 | Prevent plaintext committed secrets | MVP | Example configs use secret references or env var placeholders, not real secrets |
| CONFIG-004 | Manage accounting config through UI/API | MVP | Users can configure accounting settings without manually editing config files |
| CONFIG-005 | Validate accounting config changes | MVP | Invalid account mappings, tax settings, or period settings are rejected |
| CONFIG-006 | Audit accounting config changes | MVP | Material accounting configuration changes create audit logs |
| CONFIG-007 | Support config-driven feature flags | MVP | Feature flags such as multi-entity disabled in MVP can be set through deployment config |
| CONFIG-008 | Use Markdown for documentation only | MVP | Markdown docs do not serve as authoritative machine config |
| CONFIG-009 | Support chart of accounts file configuration | MVP | Authorized user can upload or reference a chart of accounts file |
| CONFIG-010 | Support CSV chart of accounts import/export | MVP | User can import and export chart of accounts as CSV |
| CONFIG-011 | Support YAML chart of accounts configuration | MVP | User can define chart of accounts in validated YAML format |
| CONFIG-012 | Validate chart config schema | MVP | Invalid CSV rows or YAML paths are rejected with row/path-level errors |
| CONFIG-013 | Validate accounting rules before apply | MVP | Duplicate codes, invalid account types, circular hierarchy, and unsafe changes are rejected |
| CONFIG-014 | Provide dry-run preview | MVP | User can preview create/update/reject results before applying |
| CONFIG-015 | Apply chart config through accounting services | MVP | Applied changes use normal permission, validation, and audit behavior |
| CONFIG-016 | Protect accounts with history | MVP | File config cannot delete accounts or make unsafe type/control changes after postings exist |
| CONFIG-017 | Support create-only apply mode | MVP | User can add new accounts without modifying existing ones |
| CONFIG-018 | Support safe metadata update mode | MVP | User can update safe metadata such as name, description, and inactive flag where allowed |
| CONFIG-019 | Support replace draft setup mode | MVP | User can replace chart setup only before posted transactions exist |
| CONFIG-020 | Version document chart config schema | MVP | YAML chart config includes schema version and documented fields |

---

# 17. Accounting Event API Requirements

## 17.1 Purpose

The Accounting Event API is the controlled integration point for external business layers.

External systems submit accounting-relevant events. The accounting module validates, records, and posts them if valid.

## 17.2 API Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| API-001 | Submit accounting event | MVP | Authenticated client can submit valid event |
| API-002 | Require idempotency key | MVP | Event without idempotency key is rejected |
| API-003 | Handle duplicate idempotency key | MVP | Duplicate submission returns original result without duplicate posting |
| API-004 | Validate event schema | MVP | Invalid schema returns structured validation error |
| API-005 | Validate accounting mappings | MVP | Invalid account/customer/vendor references are rejected |
| API-006 | Validate permissions | MVP | Unauthorized client cannot post event |
| API-007 | Return posting result | MVP | Successful event returns accounting transaction IDs |
| API-008 | Store external reference | MVP | Event stores external system, object type, and object ID |
| API-009 | Expose event status | MVP | Client can query event status |
| API-010 | Provide webhooks | Post-MVP | Client can subscribe to posted/rejected/failed status changes |
| API-011 | Reject unknown customer references | MVP | Invoice/payment events referencing unknown customers are rejected before posting |
| API-012 | Reject unknown vendor references | MVP | Bill/vendor-payment events referencing unknown vendors are rejected before posting |
| API-013 | Do not auto-create customers/vendors from API events | MVP | API-submitted events cannot create customer/vendor accounting records implicitly |

## 17.3 Example Event: Invoice Post Request

```json
{
  "event_type": "invoice.post_requested",
  "idempotency_key": "external:invoice:INV-1001:v1",
  "external_reference": {
    "system": "external_business_layer",
    "object_type": "invoice",
    "object_id": "INV-1001"
  },
  "invoice_number": "INV-1001",
  "transaction_date": "2026-05-21",
  "customer_id": "cust_001",
  "currency": "USD",
  "lines": [
    {
      "description": "Service revenue",
      "amount": "1000.00",
      "revenue_account_id": "acct_4000",
      "tax_code_id": "tax_ca_standard"
    }
  ]
}
```

## 17.4 Example Success Response

```json
{
  "status": "posted",
  "accounting_event_id": "evt_001",
  "created_records": {
    "invoice_id": "inv_acc_001",
    "journal_entry_id": "je_001"
  }
}
```

## 17.5 Example Validation Error

```json
{
  "status": "rejected",
  "accounting_event_id": "evt_001",
  "errors": [
    {
      "code": "INVALID_REVENUE_ACCOUNT",
      "field": "lines[0].revenue_account_id",
      "message": "Revenue account does not exist or is inactive."
    }
  ]
}
```

## 17.6 Example Unknown Customer Error

```json
{
  "status": "rejected",
  "accounting_event_id": "evt_002",
  "errors": [
    {
      "code": "UNKNOWN_CUSTOMER",
      "field": "customer_id",
      "message": "Customer does not exist. Create or import the customer before submitting this event."
    }
  ]
}
```

---

# 18. API Client Authentication

## 18.1 MVP Authentication Model

MVP API clients authenticate through config-managed scoped API credentials.

The preferred method for write endpoints is **HMAC-SHA256 signed requests**.

Bearer API keys may be supported for simpler or lower-risk endpoints, but all keys must be:

- scoped
- rotatable
- revocable
- audited
- stored hashed
- never logged

OAuth 2.0 client credentials is deferred to post-MVP.

## 18.2 HMAC Request Requirements

HMAC-signed requests should include:

```txt
X-Client-Id: billing_layer
X-Timestamp: 2026-05-21T12:00:00Z
X-Nonce: 8f5f3d2c-...
X-Signature: hmac-sha256=<signature>
```

The signature is calculated over:

```txt
method + path + timestamp + nonce + body_hash
```

The server verifies:

- client exists
- client is enabled
- timestamp is within allowed skew
- nonce has not been reused
- signature is valid
- client has required scope
- event type is allowed
- request passes normal accounting validation

## 18.3 API Authentication Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| APIAUTH-001 | Define API clients in config | MVP | API clients can be configured through YAML/env-backed configuration |
| APIAUTH-002 | Store secrets outside committed config | MVP | API client secrets are referenced through environment variables or secret manager references |
| APIAUTH-003 | Support scoped API clients | MVP | Each API client has explicit scopes and allowed event types |
| APIAUTH-004 | Authenticate API requests | MVP | Unauthenticated requests to protected API endpoints are rejected |
| APIAUTH-005 | Prefer HMAC for write endpoints | MVP | Accounting event write endpoints can require HMAC-SHA256 signed requests |
| APIAUTH-006 | Validate timestamp and nonce | MVP | HMAC requests outside allowed timestamp skew or with reused nonce are rejected |
| APIAUTH-007 | Enforce client scopes | MVP | API client cannot perform actions outside configured scopes |
| APIAUTH-008 | Hash stored API secrets | MVP | Plaintext API secrets are never stored in application database or logs |
| APIAUTH-009 | Support key rotation | MVP | A client can have active and next secrets during rotation |
| APIAUTH-010 | Audit API authentication failures | MVP | Failed API authentication attempts are logged without exposing secrets |
| APIAUTH-011 | Show API client status read-only in Integration Console | MVP | Users can view configured client status, scopes, allowed event types, and recent failures |
| APIAUTH-012 | Defer OAuth client credentials | Post-MVP | OAuth 2.0 client credentials may be added later for enterprise integrations |
| APIAUTH-013 | Use YAML for API client config | MVP | API clients can be declared in a documented YAML configuration file |
| APIAUTH-014 | Validate API client config | MVP | Invalid YAML config is rejected with clear startup or validation errors |
| APIAUTH-015 | Reference secrets outside YAML | MVP | YAML config references secret env vars or secret-manager keys rather than storing plaintext secrets |

---

# 19. Permission Matrix

## 19.1 MVP Permissions

| Permission | Description |
|---|---|
| account.read | View chart of accounts |
| account.manage | Create/edit accounts |
| journal.read | View journal entries |
| journal.create | Create draft journal entries |
| journal.post | Post journal entries |
| journal.reverse | Reverse posted journal entries |
| period.manage | Create, close, lock, or reopen periods |
| ar.manage | Manage AR records |
| ap.manage | Manage AP records |
| bank.manage | Manage bank accounts and reconciliation |
| report.read | View financial reports |
| report.manage_views | Create, edit, and share saved report views |
| tax.manage | Manage tax codes |
| audit.read | View audit logs |
| user.manage | Manage users and roles |
| api.event.submit | Submit accounting events |
| api.client.read | View configured API client status |
| config.apply_chart | Apply chart of accounts YAML/CSV configuration |

## 19.2 Required Permission Behavior

- UI and API must enforce the same permissions.
- Permission failures must return clear errors.
- Permission failures must be logged when security-relevant.
- Admin users may assign roles.
- No user may bypass period locks without explicit permission and audit log.
- Report APIs must enforce the same access rules as the reporting UI.
- Applying chart of accounts file configuration requires explicit permission.

---

# 20. Accounting Edge Cases

| Edge Case | Required Behavior |
|---|---|
| Unbalanced journal entry | Reject before posting |
| Duplicate API event | Return original result; do not create duplicate records |
| Posting into locked period | Reject unless period is reopened |
| Posting into soft-closed period | Require elevated permission |
| Editing posted journal entry | Reject; require reversal or adjustment |
| Voiding posted invoice | Create reversal; preserve original |
| Partial customer payment | Reduce open balance; set status to partially paid |
| Customer overpayment | Create unapplied credit |
| Applying payment to voided invoice | Reject |
| Vendor overpayment | Create unapplied vendor credit |
| Partial payment under cash-basis reporting | Allocate proportionally across invoice/bill lines |
| Unapplied customer payment under cash-basis reporting | Do not classify as revenue until applied, unless policy later changes |
| Tax code changed after posting | Do not mutate historical transaction |
| External object deleted | Preserve accounting record and external reference |
| Failed posting midway | Roll back atomically or complete safely; never leave partial ledger impact |
| Bank reconciliation mismatch | Do not allow reconciliation completion |
| Account deactivated | Preserve historical transactions; block new postings unless allowed |
| Currency mismatch | Reject because multi-currency is not MVP |
| Unknown customer/vendor in external event | Reject before posting |
| External API attempts customer/vendor auto-create | Reject in MVP |
| User attempts direct production database reporting | Not supported in MVP; use reporting UI/API/export |
| Business layer attempts to send non-accounting workflow data | Reject or ignore non-accounting fields according to schema validation |
| User attempts to access multi-entity settings in MVP | Not exposed in MVP |
| API request includes non-default entity_id in MVP | Reject |
| Chart config attempts to delete account with history | Reject |
| Chart config attempts unsafe type/control-account change after posting | Reject |
| API authentication request reuses nonce | Reject |
| API authentication request has stale timestamp | Reject |

---

# 21. Non-Functional Requirements

## 21.1 Reliability

| ID | Requirement | Acceptance Criteria |
|---|---|---|
| NFR-REL-001 | Atomic posting | Partial journal postings must never persist |
| NFR-REL-002 | Durable records | Posted accounting records survive restart/failure |
| NFR-REL-003 | Recoverable failures | Failed events preserve enough information for retry/debugging |
| NFR-REL-004 | Backup support | System supports database backup and restore |

## 21.2 Security

| ID | Requirement | Acceptance Criteria |
|---|---|---|
| NFR-SEC-001 | Authentication | All non-public API requests require authentication |
| NFR-SEC-002 | Authorization | All material actions require permission checks |
| NFR-SEC-003 | Encryption in transit | Production deployments use TLS |
| NFR-SEC-004 | Sensitive data protection | Secrets are not stored in plaintext application config |
| NFR-SEC-005 | Audit security events | Material permission failures are logged |
| NFR-SEC-006 | No direct write access to accounting tables | Users and external systems cannot bypass application services to mutate accounting records |
| NFR-SEC-007 | No plaintext API secrets | API keys and HMAC secrets are not stored or logged in plaintext |
| NFR-SEC-008 | API request replay protection | HMAC requests validate timestamp and nonce |

## 21.3 Performance

| ID | Requirement | Acceptance Criteria |
|---|---|---|
| NFR-PERF-001 | Journal posting latency | MVP posting should complete within acceptable operational latency for normal SMB transaction volume |
| NFR-PERF-002 | Report generation | Trial balance, P&L, and balance sheet should generate efficiently for hundreds of thousands of rows |
| NFR-PERF-003 | API idempotency lookup | Duplicate event detection should be indexed and efficient |
| NFR-PERF-004 | Reporting isolation | Reporting should not require users to run arbitrary queries against production tables |

## 21.4 Deployment and Platform Agnosticism

| ID | Requirement | Acceptance Criteria |
|---|---|---|
| NFR-DEP-001 | Containerized deployment | Application can run in Docker-based environment |
| NFR-DEP-002 | Environment configuration | Config is environment-specific and not hardcoded |
| NFR-DEP-003 | Managed deployment support | Architecture does not prevent hosted operation post-MVP |
| NFR-DEP-004 | Database migrations | Migrations are versioned and repeatable |
| NFR-DEP-005 | Platform-agnostic access | Users can access core accounting functionality through a modern web browser without installing OS-specific desktop software |
| NFR-DEP-006 | Platform-agnostic hosting | Server application can be deployed without requiring Windows-specific infrastructure |
| NFR-DEP-007 | Container-first deployment | Application supports containerized deployment suitable for Linux-based hosts |
| NFR-DEP-008 | Cloud-provider neutrality | Application does not require a specific cloud provider for core functionality |
| NFR-DEP-009 | Optional native clients only | Any future native app must be optional and must not contain accounting capabilities unavailable in the web application |
| NFR-DEP-010 | Use PostgreSQL as MVP production database | MVP production deployments use PostgreSQL as the supported database |
| NFR-DEP-011 | Provide PostgreSQL container setup | Docker-based deployment includes PostgreSQL configuration suitable for local/self-hosted use |
| NFR-DEP-012 | Version PostgreSQL migrations | All schema changes are managed through versioned migrations |
| NFR-DEP-013 | Do not require SQLite for production | SQLite is not the official production database for MVP |

---

# 22. Reporting Definitions

## 22.1 Trial Balance

Must include:

- account code
- account name
- debit balance
- credit balance
- date range or as-of date
- company/workspace context

Acceptance criteria:

- total debits equal total credits
- report ties to posted journal lines only
- draft transactions excluded
- report is ledger-based

## 22.2 Balance Sheet

Must include:

- assets
- liabilities
- equity
- as-of date
- company/workspace context
- basis label where applicable

Acceptance criteria:

- assets equal liabilities plus equity
- report uses posted entries only
- cash-basis balance sheet is limited or post-MVP unless separately specified

## 22.3 Profit and Loss

Must include:

- income
- cost of goods sold, if configured
- expenses
- net income
- date range
- company/workspace context
- basis: cash or accrual

Acceptance criteria:

- accrual-basis P&L uses posted invoice/bill and journal activity
- cash-basis P&L uses payment activity and payment applications where applicable
- report reconciles to ledger detail where applicable for selected basis
- report clearly displays selected basis

## 22.4 AR Aging

Must include:

- customer
- invoice
- due date
- open balance
- aging buckets

Acceptance criteria:

- total AR aging equals AR control account balance, except documented reconciling items
- AR aging is open-balance tracking, not cash-basis revenue recognition

## 22.5 AP Aging

Must include:

- vendor
- bill
- due date
- open balance
- aging buckets

Acceptance criteria:

- total AP aging equals AP control account balance, except documented reconciling items
- AP aging is open-balance tracking, not cash-basis expense recognition

## 22.6 Tax Liability Report

Must include:

- tax code
- taxable amount
- tax collected
- tax liability account
- date range

Acceptance criteria:

- report uses posted transactions only
- report reconciles to tax liability accounts where applicable
- supports MVP US/California tax scope

---

# 23. Import / Export Requirements

| ID | Requirement | Priority | Acceptance Criteria |
|---|---|---|---|
| IMPORT-001 | Import chart of accounts CSV | MVP | Valid CSV creates accounts; invalid rows return row-level errors |
| IMPORT-002 | Import customers CSV | MVP | Valid CSV creates customer accounting records |
| IMPORT-003 | Import vendors CSV | MVP | Valid CSV creates vendor accounting records |
| IMPORT-004 | Import opening balances CSV | MVP | Opening balances create balanced journal entry |
| IMPORT-005 | Export chart of accounts CSV | MVP | User can export accounts to CSV |
| IMPORT-006 | Export journal entries CSV | MVP | User can export journal entries and lines |
| IMPORT-007 | Export financial reports CSV | MVP | User can export reports to CSV |
| IMPORT-008 | Export saved report view output CSV | MVP | User can export configured report output to CSV |

CSV is the only required general import/export format for MVP.

YAML is required only for selected configuration use cases: chart of accounts configuration and API client configuration.

---

# 24. Agentic AI Implementation Readiness

This section exists specifically to make the PRD implementable by engineering teams and agentic AI coding systems.

## 24.1 Implementation Decomposition

Agents should decompose implementation into these epics:

1. Project foundation
2. PostgreSQL schema and migrations
3. Authentication and authorization
4. Company/workspace context
5. Hidden default entity model
6. Core Accounting UI shell
7. Chart of accounts
8. YAML chart configuration and CSV chart import/export
9. Accounting periods
10. Journal entry service
11. Posting engine
12. Audit log service
13. AR service and invoice numbering
14. AP service
15. Banking service
16. Reconciliation service
17. Cash/accrual reporting basis support
18. Reporting service
19. Report Builder Lite
20. Accounting Event API
21. HMAC API authentication
22. YAML API client configuration
23. Integration console
24. CSV import/export
25. Test suite
26. Containerized deployment packaging

## 24.2 Required Implementation Artifacts

For each requirement ID, implementation should include where applicable:

- database schema
- PostgreSQL migration
- model/entity definition
- service method
- validation logic
- permission check
- API endpoint
- UI screen or flow
- audit logging
- automated tests
- error handling
- documentation

## 24.3 Agent Guardrails

Agentic AI systems must not:

- implement non-accounting business workflows
- add CRM-style functionality
- add industry-specific business fields unless required for accounting
- add property, logistics, legal case, field service, project, or job-management screens
- allow direct writes to ledger lines from external systems
- permit destructive edits to posted accounting records
- ignore idempotency for accounting event APIs
- implement reports that include draft transactions unless explicitly required by the report definition
- bypass permission checks in API routes
- silently mutate locked-period transactions
- expose internal production tables as the reporting interface
- implement write-capable database access for users or external systems
- build reports directly from draft or mutable transaction tables unless explicitly required by report definition
- allow report views to query external business-layer data directly
- expose multi-entity UX, APIs, reports, consolidations, or intercompany behavior in MVP
- require Windows, macOS, or Linux desktop software for core accounting functionality
- auto-create customer or vendor records from external accounting events in MVP
- use fuzzy name matching to infer customer/vendor identity for posting
- hardcode the system to cash-only or accrual-only behavior
- implement OAuth as MVP unless explicitly re-decided
- store API secrets in plaintext
- log API keys, bearer tokens, HMAC secrets, or full authorization headers
- apply chart of accounts YAML/CSV files directly to database tables
- use Markdown as authoritative machine-readable configuration
- require JSON configuration in MVP
- implement production behavior that depends on SQLite-specific semantics

Agentic AI systems should:

- implement a Core Accounting UI, not a business application UI
- use ledger-backed, accounting-approved report views or service-layer queries
- implement AR/AP screens only as accounting workflows
- keep invoice and bill screens as accounting records, not customizable business forms
- use a browser-based primary UI
- support container-first deployment
- target PostgreSQL for production schema, migrations, constraints, and report queries
- use database transactions for posting operations
- include internal `entity_id` fields where appropriate for accounting records
- automatically assign the hidden default entity in MVP
- store sufficient transaction and payment relationship data to support both cash-basis and accrual-basis reporting
- clearly label report basis in generated reports
- use proportional allocation for partial payments in MVP unless overridden by future decision
- support declarative chart of accounts setup through validated YAML and CSV
- always provide dry-run preview before applying chart configuration
- use HMAC-signed requests for accounting event writes where feasible
- reject reused nonces and stale timestamps for HMAC requests
- keep API client management config-based in MVP
- use YAML for API client configuration
- use CSV as the only required general import/export format

## 24.4 Suggested Implementation Sequence

| Phase | Deliverable |
|---|---|
| 1 | Core schema: company workspace, hidden default entity, users, roles, accounts, periods |
| 2 | PostgreSQL migrations and containerized database setup |
| 3 | Browser-based UI shell and navigation |
| 4 | Chart of accounts UI, CSV import/export, YAML config dry-run/apply |
| 5 | Journal entries, journal lines, posting engine |
| 6 | Audit logs and permission enforcement |
| 7 | Trial balance, balance sheet, P&L |
| 8 | Cash/accrual reporting basis support |
| 9 | AR invoices, invoice numbering, and customer payments |
| 10 | AP bills and vendor payments |
| 11 | Banking and reconciliation |
| 12 | Report Builder Lite, saved views, drill-down, CSV export |
| 13 | YAML API client config and HMAC authentication |
| 14 | Accounting Event API |
| 15 | Integration console |
| 16 | CSV import/export |
| 17 | Hardening, edge cases, deployment |

---

# 25. Test Plan Seed

## 25.1 Ledger Integrity Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-GL-001 | Post balanced journal entry | Entry posts successfully |
| TEST-GL-002 | Post unbalanced journal entry | Entry is rejected |
| TEST-GL-003 | Reverse posted journal entry | Reversal entry is created |
| TEST-GL-004 | Edit posted journal entry | Edit is rejected |
| TEST-GL-005 | Trial balance after postings | Debits equal credits |

## 25.2 Period Control Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-PERIOD-001 | Post into open period | Posting succeeds |
| TEST-PERIOD-002 | Post into locked period | Posting fails |
| TEST-PERIOD-003 | Reopen locked period | Requires permission and reason |
| TEST-PERIOD-004 | Reopen period | Audit log is created |

## 25.3 API Idempotency and Validation Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-API-001 | Submit event once | Event posts |
| TEST-API-002 | Submit same idempotency key twice | Second call returns original result |
| TEST-API-003 | Submit invalid account ID | Event rejected |
| TEST-API-004 | Submit unauthorized event | Event rejected |
| TEST-API-005 | Submit invoice with unknown customer | Event rejected |
| TEST-API-006 | Submit bill with unknown vendor | Event rejected |
| TEST-API-007 | Submit event attempting customer auto-create | Event rejected |

## 25.4 API Authentication Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-AUTH-001 | Submit unsigned request to protected write endpoint | Request rejected |
| TEST-AUTH-002 | Submit HMAC request with valid signature | Request accepted if authorized |
| TEST-AUTH-003 | Submit HMAC request with stale timestamp | Request rejected |
| TEST-AUTH-004 | Reuse HMAC nonce | Request rejected |
| TEST-AUTH-005 | Use client without required scope | Request rejected |
| TEST-AUTH-006 | Load invalid API client YAML | Config validation fails clearly |

## 25.5 AR Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-AR-001 | Create draft invoice | No ledger impact |
| TEST-AR-002 | Post invoice | AR and revenue entries created |
| TEST-AR-003 | Record partial payment | Invoice partially paid |
| TEST-AR-004 | Record overpayment | Unapplied credit created |
| TEST-AR-005 | Void posted invoice | Reversal entry created |
| TEST-AR-006 | Create invoice in UI | System can generate unique invoice number |
| TEST-AR-007 | Submit external invoice number | System preserves supplied invoice number |

## 25.6 AP Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-AP-001 | Create draft bill | No ledger impact |
| TEST-AP-002 | Post bill | AP and expense entries created |
| TEST-AP-003 | Record partial payment | Bill partially paid |
| TEST-AP-004 | Apply vendor credit | Payable balance reduced |
| TEST-AP-005 | Void posted bill | Reversal entry created |

## 25.7 Reporting Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-REPORT-001 | Generate trial balance | Debits equal credits |
| TEST-REPORT-002 | Generate balance sheet | Assets equal liabilities plus equity |
| TEST-REPORT-003 | Generate accrual-basis P&L | Income and expenses match accrual rules |
| TEST-REPORT-004 | Generate cash-basis P&L | Income and expenses follow payment/application rules |
| TEST-REPORT-005 | Generate AR aging | Total matches AR balance |
| TEST-REPORT-006 | Generate AP aging | Total matches AP balance |
| TEST-REPORT-007 | Save report view | View stores filters, basis where supported, grouping, columns, and sort |
| TEST-REPORT-008 | Load saved report view | Report regenerates from saved configuration |
| TEST-REPORT-009 | Drill down from report line | Supporting accounting transactions are displayed |
| TEST-REPORT-010 | Attempt arbitrary SQL report | Not available in MVP |
| TEST-REPORT-011 | Report basis label | Report clearly displays cash or accrual basis where applicable |

## 25.8 Core Accounting UI Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-UI-001 | Access application from browser | Core accounting UI loads |
| TEST-UI-002 | Create journal entry from UI | UI action calls accounting service and creates draft |
| TEST-UI-003 | Unauthorized user posts journal entry | UI blocks action or API rejects request |
| TEST-UI-004 | User completes AR flow | User can create invoice, post, record payment, and view aging |
| TEST-UI-005 | User completes AP flow | User can create bill, post, record payment, and view aging |
| TEST-UI-006 | User completes reconciliation flow | Reconciliation completes only when balances match |
| TEST-UI-007 | User views audit log | Material accounting actions are visible |
| TEST-UI-008 | User views read-only API client status | Integration Console displays client status without exposing secrets |

## 25.9 Platform and Database Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-DEP-001 | Access UI from Windows browser | Core workflows are available |
| TEST-DEP-002 | Access UI from macOS browser | Core workflows are available |
| TEST-DEP-003 | Access UI from Linux browser | Core workflows are available |
| TEST-DEP-004 | Deploy server in containerized Linux environment | Application runs without Windows-specific dependency |
| TEST-DEP-005 | Attempt to use native desktop-only functionality | No core functionality requires native desktop client |
| TEST-DB-001 | Run PostgreSQL migrations | Schema applies cleanly |
| TEST-DB-002 | Posting transaction fails midway | Database transaction prevents partial ledger impact |

## 25.10 Configuration Tests

| Test ID | Scenario | Expected Result |
|---|---|---|
| TEST-CONFIG-001 | Import chart of accounts CSV | Valid rows import; invalid rows return row-level errors |
| TEST-CONFIG-002 | Apply chart of accounts YAML dry-run | Preview shows create/update/reject results |
| TEST-CONFIG-003 | YAML chart contains duplicate account code | Validation rejects config |
| TEST-CONFIG-004 | YAML chart creates circular hierarchy | Validation rejects config |
| TEST-CONFIG-005 | YAML chart attempts unsafe type change after posting | Validation rejects config |
| TEST-CONFIG-006 | YAML API client references plaintext secret | Config validation rejects or warns according to policy |
| TEST-CONFIG-007 | Markdown config supplied as machine config | Not accepted as authoritative config |

---

# 26. Success Metrics

| Metric | Target |
|---|---|
| Ledger balance integrity | 100% of posted transactions balance |
| Unbalanced posting prevention | 100% rejected before ledger impact |
| Duplicate event prevention | 100% duplicate idempotency keys return original result |
| Audit coverage | 100% of material accounting actions create audit logs |
| Locked-period enforcement | 100% of unauthorized locked-period postings rejected |
| Report consistency | Trial balance, balance sheet, AR aging, and AP aging reconcile to ledger |
| Accounting basis flexibility | Workspace can default to cash or accrual basis, and supported reports clearly display selected basis |
| MVP usability | User can complete core accounting loop from setup to transaction entry to report |
| Core UI usability | User can operate the accounting module without a connected business layer |
| API usability | External business layer can submit valid invoice, payment, bill, and expense events against existing customers/vendors |
| Report usability | Advanced user can configure, save, drill into, and export standard reports |
| Configuration usability | Advanced user can manage chart of accounts through CSV import/export and YAML configuration with dry-run preview |
| Platform independence | Core accounting workflows can be completed from a browser on Windows, macOS, or Linux |
| Deployment portability | Core server deployment can run in a containerized Linux environment without Windows-specific dependencies |
| Database readiness | MVP production deployment uses PostgreSQL with versioned migrations |
| Implementation traceability | Every MVP requirement has ID, priority, and acceptance criteria |
| Agentic implementability | Requirements can be converted into epics, tickets, tests, and schemas without guessing scope |

---

# 27. Open Questions

## 27.1 Deferred Open Questions

| ID | Question | Why it can wait |
|---|---|---|
| OQ-009 | Should attachments be supported for accounting records? | Useful, but not required for the core accounting loop |
| OQ-011 | Should post-MVP include a read-only SQL analytics replica with documented accounting views? | Already explicitly post-MVP |
| OQ-013 | What browser versions are officially supported? | Needed before QA/release, but not before implementation planning |

## 27.2 Implementation-Plan Blockers

There are no remaining open questions currently marked as blockers to implementation planning.

---

# 28. Revised Rubric Score

| Category | Score |
|---|---:|
| Product Purpose & Vision | 5 |
| Scope Discipline | 5 |
| Target User Clarity | 4 |
| Problem Definition | 4 |
| Product Requirements | 5 |
| Non-Functional Requirements | 5 |
| Architecture & System Boundaries | 5 |
| Data Model Clarity | 5 |
| User Experience Requirements | 5 |
| API / Integration Requirements | 5 |
| Compliance & Accounting Correctness | 5 |
| Success Metrics | 5 |
| Implementation Readiness | 5 |
| Testability / Acceptance Criteria | 5 |
| Prioritization / MVP Definition | 5 |
| Agentic AI Implementability | 5 |

**Total Score: 78 / 80**

**Percentage: 97.5%**

---

# 29. Decision Log

## Decision 1 — Platform Agnosticism

LedgerOS Accounting Module must be platform-agnostic.

The product requires:

- browser-based primary UI
- container-first deployment
- no Windows-only runtime dependency
- cloud-provider neutrality
- optional-only native clients

## Decision 2 — Advanced MVP Reporting

Advanced users generate reports through configurable standard accounting reports, not a full custom report builder.

The MVP includes:

- report filters
- grouping
- visible columns where supported
- cash/accrual basis selection where supported
- sorting
- drill-down
- saved views
- CSV export
- report APIs

## Decision 3 — Database Access

MVP will not provide unrestricted direct database access for reporting.

Advanced reporting is provided through:

- reporting UI
- reporting APIs
- exports
- accounting-approved report data models

Post-MVP may support controlled read-only SQL analytics through documented views, read replicas, or an analytics data mart.

## Decision 4 — Multi-Entity

Multi-entity is not part of MVP from the user’s perspective.

MVP supports a single accounting entity per deployment or company workspace.

Multi-entity, entity-level reporting, consolidated reporting, intercompany transactions, and eliminations are deferred to Post-MVP.

## Decision 5 — Core Accounting UI

MVP must include a browser-based Core Accounting UI.

Users must be able to operate the accounting core directly without a connected business layer.

The Core Accounting UI includes only accounting-native workflows:

- setup
- GL
- AR
- AP
- banking
- reporting
- audit/controls
- integration console

It must not include non-accounting business application features.

## Decision 6 — Chart of Accounts File Configuration

Chart of accounts must support version-manageable file configuration in MVP.

The MVP will support:

- CSV for chart of accounts import/export
- YAML for declarative chart of accounts configuration
- dry-run preview before apply
- validation against schema and accounting rules
- application through normal accounting services
- audit logs for applied changes
- protections against unsafe changes after posting

## Decision 7 — Customer/Vendor Creation by External Systems

External systems may not automatically create customer or vendor records in MVP.

Customer and vendor records must already exist in the accounting module before external events can reference them.

Unknown customer/vendor references are rejected with structured validation errors.

## Decision 8 — MVP Database

MVP production database is PostgreSQL.

The expected MVP scale of a few hundred thousand rows is comfortably within PostgreSQL’s capabilities.

PostgreSQL is selected for transactional correctness, relational reporting, indexing, migrations, platform-agnostic deployment, auditability, and future analytics support.

SQLite may be used only for local testing or developer convenience, not as the official MVP production database.

## Decision 9 — Hidden Default Entity

The MVP includes an internal hidden default entity for each company/workspace.

This supports future multi-entity functionality while preserving MVP simplicity.

Users experience the MVP as a single-entity accounting system.

## Decision 10 — Cash and Accrual Reporting

MVP supports both cash-basis and accrual-basis reporting.

The business client chooses the default accounting basis at the company/workspace level.

Supported reports clearly display selected basis.

Report Builder Lite may allow authorized users to override basis per supported report.

Trial balance remains ledger-based.

AR/AP aging remains open-balance tracking.

Cash-basis P&L is MVP.

Cash-basis balance sheet is limited or post-MVP unless explicitly included later.

Partial payments use proportional allocation across invoice/bill lines in MVP unless later revised.

## Decision 11 — Invoice Number Ownership

The accounting module supports internal invoice number generation for invoices created directly in the Core Accounting UI.

External invoices use the invoice number supplied by the external business layer.

Invoice number and external object reference are stored as distinct fields.

## Decision 12 — API Client Authentication

API clients are managed by config in MVP.

API clients use scoped credentials.

HMAC-SHA256 signed requests are preferred for accounting event write endpoints.

Bearer API keys may be supported only with strict controls.

Secrets must be stored outside committed config and never stored or logged in plaintext.

API clients must have explicit scopes and allowed event types.

OAuth 2.0 client credentials is deferred to post-MVP.

## Decision 13 — File-Based Configuration Formats

MVP uses:

- CSV for general import/export
- CSV for chart of accounts import/export
- YAML for declarative chart of accounts configuration
- YAML for API client configuration

Markdown is documentation-only and is not an authoritative machine-readable configuration format.

JSON is not required for MVP configuration.
