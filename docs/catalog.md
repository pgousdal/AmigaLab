# Local catalog

The SQLite catalog under `metadata/catalog` is disposable derived state. It
contains deterministic catalog documents and an FTS5 index built from
canonical objects, files, media, sources, and verification reports.
`catalog-build` atomically replaces a validated temporary database; deleting
or rebuilding it never affects preserved content.
