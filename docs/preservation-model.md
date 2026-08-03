# Preservation object model

AmigaLab separates immutable preservation content from its own additive
metadata. Original collections are never renamed, moved, unpacked,
timestamp-normalized, or modified. README, INFO, and archive files remain in
their original hierarchy.

All AmigaLab metadata lives under `/srv/amigalab/metadata`: `collections` holds
collection descriptions and manifests; `objects` holds logical object records;
`sources` describes origins; `imports` records acquisition events; and
`verification` stores verification outcomes. No `.meta` or other AmigaLab file
is written inside a preserved collection.

JSON and YAML metadata are authoritative. SQLite and Meilisearch are optional,
disposable indexes that must be rebuildable entirely from metadata.
Import plans and conflict decisions are also canonical metadata; they are never
SQLite-only state.

## Concepts

- **Collection** is an archive context such as Aminet, Fred Fish, or coverdisks.
- **Object** is one logical item, with a stable ID formed as
  `collection:original/relative/path`.
- **File** is every stored file that belongs to an object, including sidecars.
  Each file stores MD5, SHA-1, SHA-256, SHA-512, size, original filename, and
  original path.
- **Source** identifies an origin such as Aminet Live or a personal collection.
- **Import event** records the time, source, method, tool version, and result.
- **Verification event** records date, algorithm, success, and a failure reason.

Sidecars with `.readme`, `.info`, `.txt`, `.nfo`, or `.diz` suffixes that share
the primary filename stem are associated automatically. Provenance is additive:
an object retains all source IDs and import-event IDs rather than replacing a
previous origin.
