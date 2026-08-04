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

`recovery-execute PLAN_ID` acquires the plan lock, creates a checkpointed
execution document, validates dependencies, runs actions sequentially, and
updates the audit report after each durable boundary. `recovery-resume
PLAN_ID EXECUTION_ID` loads that same state and skips actions whose destination
and canonical records still verify. Actions left `running` are treated as
interrupted and are revalidated before retry. A plan with a missing or changed
source becomes stale and is blocked; it is never regenerated implicitly.

Execution-state JSON is authoritative for orchestration progress, while
canonical object, verification, provenance, and relationship records remain
authoritative for preservation evidence. Reports are derived summaries and may
be regenerated without changing execution semantics.

Exit status is 0 for ready/successful work, 1 for blocked, stale, conflict, or
invalid input, and 2 for operational failures. A per-plan lock prevents two
writers from executing the same plan. Lock failures are conservative and do
not remove an existing lock automatically.
