# Non-destructive import workflow

AmigaLab registers and scans preservation material before copying it. Metadata
under `/srv/amigalab/metadata` is canonical; SQLite and Meilisearch indexes are
rebuildable conveniences, not sources of truth.

## Source registration

Register directory, ISO, archive, or mounted-filesystem provenance first:

```sh
python3 scripts/amigalab-import.py source-add \
  --id aminet-cd-17 --name 'Aminet CD 17' --kind directory \
  --location /mnt/Aminet-CD
```

ISO and archive source kinds are recorded for provenance but are not extracted
in M2.2. Directory and mounted filesystem locations support scanning.

## Scan and import

`scan` is read-only and produces a preview of new, existing, changed, and
conflicting logical objects:

```sh
python3 scripts/amigalab-import.py scan /mnt/Aminet-CD --collection aminet
```

An import requires explicit `--yes`. It hashes material, writes only additive
metadata, copies files through `/srv/amigalab/staging`, and then copies them to
the selected collection with the original relative paths and `copy2` timestamps.
No source files are changed, renamed, moved, unpacked, or deleted. Existing
SHA-256 matches are not copied again; their provenance is appended instead.

```sh
python3 scripts/amigalab-import.py import /mnt/Aminet-CD \
  --collection aminet --source aminet-cd-17 --yes
```

Use `verify --collection aminet` to append object-level verification events.

For original media, use `media-scan` and `media-import`. The latter requires
`--yes`, records a media hash/license profile, and copies the image only to the
dedicated media root; it does not copy commercial or unknown contents into a
collection. `transaction-status`, `transaction-resume`, and
`conflict-report` expose durable import state and operator decisions.

Selective plans are canonical metadata and must be approved before execution:

```sh
python3 scripts/amigalab-import.py plan-create /mnt/source \
  --source synthetic-source --collection aminet --mode members-only \
  --path util/example.lha
python3 scripts/amigalab-import.py plan-show PLAN_ID
python3 scripts/amigalab-import.py plan-approve PLAN_ID
```

Commercial and licensed media defaults to `media-only`; explicit member import
requires an operator-selected mode and license policy review. Blocking conflicts
are never overwritten automatically.

## Indexes

Build, delete, or query the optional SQLite index at
`/srv/amigalab/metadata/index.db` with:

```sh
python3 -m scripts.preservation.index build-index
python3 -m scripts.preservation.index query DiskMaster
python3 -m scripts.preservation.index drop-index
```
# Recovery and durable operations

Approved imports are represented by canonical transaction entries.  Recovery
uses the persisted entry state rather than rescanning selection rules.  Staging
files are transaction-owned temporary files; destination placement uses an
atomic temporary copy followed by verification.  A resume validates staged
content, reuses verified destinations, and completes only missing metadata,
provenance, relationships, import events, and verification events.

Every imported file is hashed with MD5, SHA-1, SHA-256, and SHA-512 in one
streaming pass where practical.  Verification and media/member relationship
records are stored under `metadata/` and are idempotent by operation key, so a
resume does not duplicate successful history.  Media-and-members imports keep
the media entry and member entries independent: a failed member can be retried
without recopying an already verified media image.

Use `transaction-status` to inspect entry-derived counters and
`transaction-reconcile` for a read-only consistency report.  Temporary files
are never interpreted as preserved content, and differing destination content
is always a blocking conflict rather than an overwrite.
