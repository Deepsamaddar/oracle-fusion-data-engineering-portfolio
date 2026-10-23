# Oracle integration design

Deep Samaddar · Portfolio design notes · Reviewed 23 October 2026

## What is implemented

This repository generates local JSON pages and CSV files, validates their manifests, and loads a canonical SQLite warehouse. It contains **no live Oracle connector**. Field names are my normalized contract, not a claim about Oracle response fields or a tenant's extract metadata.

## Source-to-contract mapping to implement in a tenant

| Scenario | Candidate source area | Mapping work needed |
|---|---|---|
| APAC procurement | Purchase orders and lines/schedules, receiving records, invoice lines | Join at a stable order-line grain; aggregate receipts without duplicating invoice lines; handle units, cancellation and return semantics |
| EMEA payables | Payables invoices, installments, payment/application data | Choose invoice or installment grain; derive paid and outstanding amounts; preserve the correct due date and source modification version |
| Americas close | Supported general-ledger journal header/line extract | Resolve the actual supported extract objects in tenant metadata; map ledger, period, entered currency, debit and credit; define posting/status filters |

Oracle documents the Financials invoices collection at `/fscmRestApi/resources/11.13.18.05/invoices` and Procurement purchase orders at `/fscmRestApi/resources/11.13.18.05/purchaseOrders`. A collection endpoint is only a starting point: child resources, permissions and available fields must be checked against the tenant release. This portfolio does not invent a universal journal extract object name.

## Extraction choices

For a real project I would confirm the tenant release, licensed features, supported objects, expected volume and freshness target before choosing an extraction method. Oracle documents REST resources and BICC bulk extraction. Its newer Data Extraction Tool documentation also describes a long-term replacement path for BICC. BICC should therefore not be treated as the only current design option.

A production design could land supported extracts in OCI Object Storage, validate completeness, transform them into a canonical contract, and merge them into a managed warehouse. Those cloud components are **proposed architecture**, not deployed resources in this repository.

Incremental extraction needs a bounded overlap window, stable per-record versions and deduplication. The local watermark is observational; the loader accepts unseen older records. It does not implement the upstream extraction window or guarantee that a source never omits data. Source deletion events, snapshot reconciliation and business corrections need an explicit policy.

## Before a live connection

1. Validate source grains, IDs, relationships and modification timestamps against authorized tenant metadata and representative extracts.
2. Configure least-privilege access through the approved secret manager; never put credentials or real finance extracts into this public repository.
3. Implement pagination, retry/backoff, rate-limit handling and source snapshot consistency. Create a manifest only after verifying all parts and upstream job status.
4. Replace local SQLite and in-memory parsing as volume requires; add partitioning, orchestration, metrics, alerting, retention and replay controls.
5. Reconcile control totals with the source, test deletes and corrections, and agree data ownership and currency/precision rules with finance.

## Official references

- [Financials REST API, release 26C](https://docs.oracle.com/en/cloud/saas/financials/26c/farfa/index.html)
- [Get all invoices, release 26A](https://docs.oracle.com/en/cloud/saas/financials/26a/farfa/op-invoices-get.html)
- [Purchase orders REST resources, release 26A](https://docs.oracle.com/en/cloud/saas/procurement/26a/fapra/api-purchase-orders.html)
- [BICC overview, release 26B](https://docs.oracle.com/en/cloud/saas/applications-common/26b/biacc/overview-of-business-intelligence-cloud-connector.html)
- [Data Extraction Tool overview, release 26A](https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faude/overview-of-the-data-extraction-tool.html)
- [Procurement Data Extraction Tool, release 26C](https://docs.oracle.com/en/cloud/saas/procurement/26c/fainp/prc-data-extraction-tool.html)

These references explain product integration concepts; they do not certify this local demo or establish compatibility with an untested tenant.
