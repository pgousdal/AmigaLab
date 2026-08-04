# External source inspection

M2.15 adds a canonical registry for external metadata sources. Records live in
`metadata/external-sources`; checks and immutable normalized snapshots live in
`metadata/external-checks` and `metadata/external-snapshots`. The registry is
separate from preserved objects and never makes upstream metadata authoritative.

The initial provider is Internet Archive. It is restricted to official HTTPS
endpoints and uses metadata APIs only. File bodies, torrents, and media are
never downloaded. Upstream hashes are retained as `upstream-reported`, not
locally verified preservation hashes.

Offline operations can list sources and snapshots, compare snapshots, and
create mirror plans. A removed upstream item is recorded as a change and never
deletes local preservation content.
