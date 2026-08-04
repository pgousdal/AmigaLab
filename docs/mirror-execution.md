# Approved mirror execution

M2.17 executes only an explicitly approved mirror plan. Execution state and
per-file acquisition entries are canonical JSON under `metadata/`
(`mirror-executions` and `mirror-acquisition-entries`). Partial content is
kept under `staging/mirror-executions/<execution-id>/` and is never presented
as preserved media until size, upstream hashes, local MD5/SHA-1/SHA-256/SHA-512,
and destination containment have been verified.

```text
approved mirror plan
        ↓ --yes
serial HTTPS acquisition
        ↓
partial staging → four-hash verification → atomic media placement
        ↓
canonical media/provenance metadata
```

Only official Internet Archive HTTPS URLs are accepted. HTTP, FTP, local,
private-address, and unapproved-host URLs are rejected. The client streams
responses and supports a transaction-owned partial file for later resume; it
does not execute torrents, extract archives, or import files into collections.

Matching existing media is reused after local verification. Different content
at the approved destination blocks execution and is never overwritten.

Commands:

```bash
amigalab-import mirror-execute PLAN_ID --yes
amigalab-import mirror-status EXECUTION_ID --json
amigalab-import mirror-resume EXECUTION_ID --yes
amigalab-import mirror-report EXECUTION_ID
amigalab-import mirror-cancel EXECUTION_ID
```

Cancellation retains completed media, metadata, and partial staging. A later
explicit cleanup operation is required to remove partial data. Successful
acquisition is local preservation preparation only; collection import remains
a separate future plan.
