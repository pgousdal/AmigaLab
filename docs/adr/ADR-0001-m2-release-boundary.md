# ADR-0001: M2 release boundary

## Decision

Release AmigaLab v0.2.0 as the completed M2 preservation platform.

## Rationale

The platform now covers canonical preservation, external inspection,
approved acquisition/import, verification, recovery, cataloging, operations,
and local read-only presentation. Further work is primarily compatibility or
M3 product scope rather than a missing M2 boundary.

Canonical JSON/YAML metadata and preserved files are authoritative. SQLite,
Meilisearch, reports, and the web layer are disposable or derived. AmigaLab
and CommodoreLab remain separate projects with namespaced resources and
coexistence expectations.

## Compatibility

Future M2 fixes may improve adapters, reporting, and compatibility. They must
not silently change historical paths or weaken approval and read-only safety
boundaries. M3 begins development and museum workflows rather than replacing
the preservation model.
