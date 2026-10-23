# Validation and interview notes

**Deep Samaddar — original Oracle Fusion–inspired portfolio**

## Reproduce the evidence

Run the README commands from the repository root. The 28 unit/integration tests cover all three contracts, duplicate records across pages, checksum and row-count failures, incomplete extracts, unsafe paths, missing keys, numeric validation, currency separation, aging boundaries, journal grouping, equal-version conflicts, stale updates, late arrivals, replay, HTML escaping and a transaction rollback followed by a successful retry.

The default fresh demo reads 909 base input rows (303 per scenario), accepts 900, and quarantines nine. An incremental two-row batch inserts one and updates one, leaving 901 current records. There are four committed run-audit entries and three scenario watermarks. Replaying the same batches leaves these counts unchanged. A replay response contains the original run statistics with `replayed: true`; those numbers are not new inserts.

The default analytics report 113 APAC exception records, 229 EMEA overdue invoices, and 15 unbalanced Americas journals out of 150. Reference date: 2026-10-23. The report is a synthetic example, not a performance benchmark or a production audit opinion.

GitHub Actions runs the tests and the demo twice on Python 3.10, 3.11 and 3.12. Consult the live workflow result for remote status. Local verification used Python 3.12.

## Design choices I can discuss

**Why keep a manifest?** I want to distinguish a missing or changed extract from bad individual business data. A broken file set must not produce a seemingly successful partial load.

**Why keep rejected rows?** A rejected record needs a reason and source position so it can be corrected and traced. The demonstration keeps the raw synthetic payload. A production quarantine needs restricted access and retention rules.

**Why not filter everything below the watermark?** An older invoice can arrive for the first time. I compare source versions per key and accept unseen keys; the extraction process must independently implement a suitable overlap window.

**What happens during a crash?** Records, rejects, run audit and watermark share one transaction. The failure-injection test raises an error before commit and verifies that none of those tables were partially updated.

**Why Decimal?** Financial calculations should not inherit binary floating-point rounding artifacts. I also keep currencies separate rather than pretending they can be summed directly.

**What did I simplify?** Source extraction and mapping are simulated. SQLite and whole-extract parsing keep the demonstration portable. A production implementation requires tenant validation, orchestration, durable storage and operational controls.

## Known limitations and recovery

- No network client, cloud deployment, deletion/tombstone handling, historical dimension model, FX conversion, tax engine or tenant compatibility claim.
- Entire extracts are read in memory. The demonstrated scale is 901 current records; no enterprise throughput claim is made.
- Equal source timestamp with different contents is rejected rather than arbitrarily choosing a winner. A corrected source version or controlled repair is required.
- Repeated IDs within one batch are rejected after the first valid occurrence. Source mapping should establish deterministic ordering and grain before loading.
- Batch identity uses the manifest hash, not the validation-code version. Changed validation rules do not automatically reprocess a committed batch. For this demo, replay from source into a new output database; a production system needs a versioned, audited reprocessing procedure.
- A hash validates bytes against a supplied manifest; it does not authenticate the producer or prove the source was complete. Trusted upstream job checks remain necessary.
- Procurement is a simplified line control; payables has one due date per invoice; journal balance is only one month-end control.

## Portfolio description

Use after reviewing and being able to explain the implementation:

> Developed an Oracle Fusion–inspired data engineering portfolio covering APAC procurement, EMEA payables aging and Americas journal controls. Implemented manifest validation, incremental upserts, quarantine, atomic audit tracking and replay protection in Python and SQLite; validated the workflow with 28 automated tests and reproducible synthetic data.

Present this as a personal, AI-assisted project. Describe live Oracle/OCI integration as the next implementation step, not as completed client experience. All names and ownership statements in this original repository identify Deep Samaddar.
