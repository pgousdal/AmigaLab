# External source inspection

M2.15 adds a canonical registry for external metadata sources. Records live in
`metadata/external-sources`; checks and immutable normalized snapshots live in
`metadata/external-checks` and `metadata/external-snapshots`. The registry is
separate from preserved objects and never makes upstream metadata authoritative.

The initial provider is Internet Archive. It is restricted to official HTTPS
endpoints and uses metadata APIs only. File bodies, torrents, and media are
never downloaded. Upstream hashes are retained as `upstream-reported`, not
locally verified preservation hashes.

Inspection checks are resumable state machines. Each normalized page is an
atomic checkpoint under `metadata/external-checkpoints/<check-id>/`; completed
pages are not fetched again. Completed snapshots are finalized only after all
checkpoints validate. Interrupted or cancelled checks retain their history and
partial data but cannot be mistaken for completed snapshots.

Offline operations can list sources and snapshots, compare snapshots, and
create mirror plans. A removed upstream item is recorded as a change and never
deletes local preservation content.

Mirror plans are proposals. They can be validated, reviewed, approved,
cancelled, or superseded by a newer revision. Approval is bound to exact plan,
source, and snapshot fingerprints. `mirror-plan-preview` shows future locators
and paths without creating files or issuing content requests.
