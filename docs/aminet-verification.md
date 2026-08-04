# Aminet verification

M2.20 verifies preserved Aminet content without changing it. `aminet-verify`
and `verification-report-create` read canonical object/file records and the
configured collection tree. Policies are `metadata-only`, `sha256`, and
`full-hashes`; metadata-only is not an integrity check. Reports are canonical
JSON under `metadata/verification-reports` and are derived evidence, not the
authority.

The verifier checks containment, hierarchy, regular files, size, hashes,
import/verification event references, and untracked files. Sidecar extensions
(`.readme`, `.info`, `.txt`, `.nfo`, `.diz`) are counted and relationship
findings remain warnings unless a selected relationship is missing.

`collection-reconcile` is read-only. `collection-repair-plan` proposes only
deterministic metadata actions; it never edits collection or media content.
Legacy records remain readable when optional relationship fields are absent.

