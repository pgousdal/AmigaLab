# Mirrored media analysis

M2.18 keeps acquisition and collection import separate:

```text
verified local media → read-only analysis → draft import plan
                  → separate plan validation and approval
```

Analysis is eligible only for completed or reused acquisition entries whose
local media hashes still verify. ZIP and TAR members are enumerated without
extraction; ISO uses the optional userspace adapter and never mounts images.
Unsafe paths, links, special entries, and normalized collisions remain visible
findings and cannot be silently sanitized.

Aminet evidence includes known top-level categories and `.readme` stem pairs.
The original hierarchy is retained and the media image remains a separate
provenance source. Commercial, licensed, personal-backup, and unknown media
receive conservative recommendations; ROM and Workbench candidates are only
reported, never installed.

`import-plan-from-media` creates an ordinary draft import plan and a separate
traceability link. Mirror approval does not approve the import plan, and no
collection file is copied by analysis or plan generation.
