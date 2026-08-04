# Changelog

## [0.2.0] - 2026-08-04

### Added

- Completed the M2 preservation, acquisition, import, verification, catalog,
  operations, and local presentation platform.

### Architecture

- Added namespaced standalone/coexistence Ansible architecture, canonical
  metadata, append-only history, transaction recovery, and rebuildable SQLite
  indexes.

### Preservation

- Added immutable collections, four-hash file records, licensed-media
  classification, provenance, ISO/directory/ZIP/TAR adapters, and Aminet
  hierarchy and `.readme` preservation.

### Acquisition and Import

- Added external source inspection, resumable snapshots, change reports,
  mirror-plan lifecycle, approved resumable HTTPS acquisition, media analysis,
  and separately approved Aminet imports.

### Verification and Search

- Added collection verification, traceability, reconciliation, repair
  planning, SQLite FTS5 cataloging, `.readme` indexing, and a local read-only
  web interface with optional Meilisearch synchronization.

### Operations and Security

- Added opt-in scheduled operations, conservative retention controls,
  namespaced locks, localhost-only web defaults, and read-only boundaries.

### Known Limitations

- See [the v0.2.0 release notes](docs/releases/v0.2.0.md).
