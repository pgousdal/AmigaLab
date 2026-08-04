# Recovery planning and audit workflow

M2.13 stores deterministic recovery plans under `metadata/recovery-plans`,
execution state under `metadata/recovery-executions`, reports under
`metadata/recovery-reports`, and filesystem locks under
`metadata/recovery-locks`. All documents are canonical JSON written by
temporary-file replacement.

## Lifecycle

1. Generate and inspect a plan: `amigalab-import recovery-plan TRANSACTION --write`.
2. Run `amigalab-import recovery-dry-run PLAN`; this performs validation only.
3. Execute through the existing approved transaction workflow.
4. If interrupted, reload the persisted execution state and resume incomplete
   actions after source-fingerprint validation.
5. Inspect the JSON audit report and rerun safely; matching destinations and
   existing canonical records are reported as already satisfied.

Plan IDs hash canonical content and exclude creation timestamps. A changed
source, sidecar set, staged hash, or destination conflict blocks execution;
plans are never silently regenerated. Dry-runs never copy files or write
verification, provenance, relationship, or execution-state records.

Exit status is 0 for ready/successful work, 1 for blocked, stale, conflict, or
invalid input, and 2 for operational failures. A per-plan lock prevents two
writers from executing the same plan. Lock failures are conservative and do
not remove an existing lock automatically.
