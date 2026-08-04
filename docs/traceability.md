# Traceability and relationship enrichment

`object-trace`, `file-trace`, and `media-trace` follow references through the
external source, snapshot, mirror execution, acquisition, analysis, import
plan, transaction, and preservation records. Missing links are reported; they
are never fabricated. Traces are offline and read-only.

Relationship enrichment is stored separately from legacy object documents so
older M2.x metadata remains compatible. Media/member and sidecar records use
stable operation identities and are safe to rebuild idempotently. A future
backfill may add missing metadata only after deterministic evidence is found.

