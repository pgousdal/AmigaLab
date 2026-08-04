# Scheduled operations

Operations are disabled by default (`amigalab_operations_enabled: false`).
When explicitly enabled, source checks, verification, and reconciliation run
through canonical CLI commands and write auditable `operations-runs` and
`operations-events` records. They may create snapshots, change reports,
verification reports, and draft mirror/repair plans, but never approve or
execute them.

`operations-preview` is a read-only deployment preview. `operations-status`,
`operations-history`, and `operations-report` work offline from metadata.

