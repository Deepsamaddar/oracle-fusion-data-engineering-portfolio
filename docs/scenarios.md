# Regional scenarios — Deep Samaddar

All companies, records and situations here are fictional. Regions provide business context and currency examples; they do not imply regional legal or tax compliance.

## APAC procurement

**Situation:** A distributor buying across India, Singapore and Australia wants a daily list of orders requiring follow-up. I model one canonical order-line record with ordered and received quantity, agreed unit price, and invoice unit price.

**Decision:** Flag under-receipt, over-receipt, or an absolute unit-price difference greater than 0.01. Open commitment is `max(ordered - received, 0) × agreed_price`, rounded to two decimals. A row can have multiple flags but counts once in the exception-record total.

**Contract:** Common fields plus `order_id`, `ordered_qty`, `received_qty`, `agreed_price`, `invoice_price`. Ordered quantity must be positive; other values are nonnegative. Allowed currencies: INR, SGD, AUD.

**Demo:** 300 current records, 113 exception records; open commitments of 1,000.00 in each currency. These totals must not be added across currencies.

**Boundary:** This is a simplified procurement control, not a full three-way matching system. Real receipts, returns, cancellations, unit conversions, invoice splits, tax and freight need additional mappings and rules. A real PO header endpoint alone cannot supply all these fields.

## EMEA payables

**Situation:** A finance team covering euro, sterling and dirham entities wants a reproducible outstanding-invoice view, even when a payment update or an older invoice arrives later.

**Decision:** Outstanding amount is `invoice_amount - paid_amount`. Age uses the explicit reference date minus due date. Due today or later is `not_due`; overdue buckets are 1–30, 31–60, 61–90 and more than 90 days. Zero outstanding is `settled` regardless of due date. Overpayments are quarantined in this simplified model.

**Contract:** Common fields plus `invoice_id`, `invoice_amount`, `paid_amount`, `due_date` (ISO date). Allowed currencies: EUR, GBP, AED.

**Demo:** Start with 300 valid invoices, apply one newer payment update and accept one previously unseen older invoice. Final current count is 301, with 229 overdue invoices as of 2026-10-23. Full aging totals are in the generated report and metrics JSON.

**Boundary:** A real invoice may have multiple installments and payment events. Map an installment-level grain or explicitly aggregate with an approved due-date policy. Credit memos, reversals, disputed invoices and payment clearing are not represented here.

## Americas month-end close

**Situation:** A shared-service team handling US, Canadian and Brazilian ledgers wants an exception list before reviewing the close.

**Decision:** Group canonical journal lines by `(ledger, period, journal_id, currency)`. Flag an absolute debit/credit difference greater than 0.01. A single line cannot contain both a positive debit and a positive credit.

**Contract:** Common fields plus `journal_id`, `ledger`, `period` (`YYYY-MM`), `debit`, `credit`. Allowed currencies: USD, CAD, BRL.

**Demo:** 300 lines form 150 journals, of which 15 intentionally have a 1.00 imbalance. Different ledgers or currencies cannot offset each other.

**Boundary:** Balance is one control, not proof that a close is complete or accounting is correct. Posting status, subledger reconciliation, balancing segments, conversion rates and period permissions require additional controls.

## Shared contract

Every record has a nonblank string `record_id`, timezone-aware ISO `updated_at`, and an allowed `currency`. Stable IDs must represent the source grain, not a display name. The current table key is `(scenario, record_id)`; a real mapping should include tenant and business-unit identity in that stable key.

Numeric fields accept finite, nonnegative values up to 1,000,000,000,000 with at most two decimal places. This deliberately narrow demonstration contract applies to quantities as well as money; it is not a universal Oracle quantity or currency precision rule. All configured currencies use two decimals in this demo.

Each manifest lists its scenario, format, ordered file paths, SHA-256 hashes and expected row count. REST-style files include `items` and `hasMore`. Paths must stay inside the manifest directory. Repeated files, bad hashes, incomplete page chains and row-count differences fail the whole extract before database writes. Invalid individual business records are retained in quarantine with their row number and reason.
