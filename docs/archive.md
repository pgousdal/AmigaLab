# Archive framework

M2.0 defines the reproducible metadata and integrity structure shared by every
preservation collection. It does not download or distribute archive content.

## Preservation rule

Collections retain their original historical organization. Import and metadata
work must not rename, move, normalize, unpack, or replace archived files.
Original directory paths, filenames, and accompanying metadata remain part of
the collection: for example, an Aminet package and its adjacent `.readme` file
are both preserved at their original paths. AmigaLab enrichment belongs only in
separate, additive metadata; it must never rewrite the source archive layout.

## Collection layout

Each supported collection under `/srv/amigalab` (`aminet`, `fish`, `magazines`,
`docs`, `ndk`, `adf`, `hdf`, `demos`, `source`, `workbench`, and `kickstarts`)
is paired with a separate metadata directory:

```text
/srv/amigalab/metadata/collections/aminet/
├── collection.yml
├── manifest.json
└── checksums.sha256
```

Run `make archive-init` to create missing collection and metadata directories.
Existing metadata and manifests are never overwritten by Ansible.

## Metadata schema

Every `collection.yml` uses these fields: `name`, `description`, `license`,
`upstream`, `maintainer`, `created`, `updated`, `verification`, and `status`.
Use ISO 8601 UTC timestamps for `created` and `updated`. `verification` is
`sha256` for M2.0. Update metadata deliberately when collection ownership,
provenance, or state changes.

## Manifest and verification

Generate controls for one collection with:

```sh
make manifest COLLECTION=aminet
```

The generator recursively records each data file's POSIX-relative path, byte
size, SHA-256 digest, and nanosecond modification time in deterministic path
order. It also writes a matching `checksums.sha256` under separate metadata.
This observes all original files, including sidecar metadata such as `.readme`
files, without modifying or excluding any of them.

Verify content later with:

```sh
make verify-archive COLLECTION=aminet
```

Verification reports missing, changed, and extra files, as well as a checksum
file that differs from the manifest. Its exit status is a bitmask: missing `2`,
changed `4`, extra `8`, checksum metadata mismatch `16`; `0` means valid and
`1` indicates an invalid collection or control file.
