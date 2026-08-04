# Offline search

`search QUERY` uses local SQLite FTS5 and works without Internet or
Meilisearch. Filters include collection, entity type, extension, path prefix,
license, verification state, and source. JSON results contain canonical IDs
for the existing trace commands.
