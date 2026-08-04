# Aminet media imports

M2.19 completes the offline boundary from verified mirrored media to a draft
or approved Aminet import transaction:

```text
verified local media → read-only analysis → draft import plan
→ separate plan approval → exact ZIP/TAR member streaming
→ transaction entries → hierarchy-preserving Aminet files
```

`plan-validate` checks the media-analysis link, local media hash, acquisition
execution, selected-member identities, and Aminet target. `plan-approve` is a
separate append-only approval from mirror approval. `plan-execute --yes` reads
only the local verified media path; it never contacts Internet Archive.

Selected `.readme` files are ordinary preserved files with their own four
hashes, import events, verification events, and `sidecar-of` relationships.
Paths such as `util/arc/example.lha` remain unchanged beneath the configured
`aminet` collection root. Existing identical files are reused; differing files
block without overwrite.

Analysis and plan generation never copy files into collections automatically.
The existing transaction and resume workflow remains responsible for recovery.
