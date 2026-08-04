# Internet Archive provider

The provider uses `advancedsearch.php` for collection membership and
`metadata/<identifier>` for item/file metadata. Requests identify themselves
as AmigaLab and use bounded timeouts. Normalized snapshots retain collection,
item, file, access, and licensing metadata plus the original public locator.

Inspection is read-only. It does not fetch file bodies, invoke torrent tools,
or write to preservation collections. Provider errors and incomplete pages are
captured in inspection-check metadata; a later check can resume from its page
cursor.
