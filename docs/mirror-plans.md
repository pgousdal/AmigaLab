# Mirror plans

A mirror plan is a proposal generated from a completed external snapshot. It
selects conservative original files, excludes derivatives and torrent files,
and rejects unsafe names. Plans include upstream locators, reported hashes,
license warnings, target category, and provenance needed by a future importer.

M2.15 intentionally has no mirror-plan execution command. Creating or
approving a plan never downloads content or changes preserved collections.
