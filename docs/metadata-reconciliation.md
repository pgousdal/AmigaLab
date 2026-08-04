# Metadata reconciliation

`collection-reconcile aminet` compares canonical metadata with the preserved
tree and reports missing/extra files, changed hashes, absent events, and
relationship gaps. It does not repair anything. `collection-repair-plan
aminet` emits a draft metadata-only plan; ambiguous source or sidecar
relationships are blocked for operator review. No repair may rename, delete,
replace, or download content.

All operations work offline. SQLite, when enabled, is disposable and rebuilt
from canonical JSON; it is never the source of a verification result or trace.

