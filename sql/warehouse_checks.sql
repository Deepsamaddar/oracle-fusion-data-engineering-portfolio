-- Deep Samaddar: SQLite warehouse controls after the default 300-row demo.
-- Run against artifacts/demo/warehouse.sqlite. No money uses floating-point SQL.
SELECT scenario, COUNT(*) AS current_records FROM records GROUP BY scenario;
-- Expected: americas_close 300, apac_procurement 300, emea_payables 301.
SELECT COUNT(*) AS committed_batches FROM runs; -- 4
SELECT COUNT(*) AS rejected_rows FROM quarantine; -- 9
SELECT scenario, updated_at AS observed_source_watermark FROM watermarks;
-- Expected: three scenarios; EMEA 2026-10-22, other two 2026-10-20 (UTC).
SELECT batch_hash, row_number, reason FROM quarantine ORDER BY batch_hash, row_number;
-- The composite primary key also enforces this invariant:
SELECT scenario, record_id, COUNT(*) AS copies
FROM records GROUP BY scenario, record_id HAVING COUNT(*) > 1; -- no rows
