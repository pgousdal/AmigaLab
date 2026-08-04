# Optional Meilisearch

SQLite remains the default local search backend. An optional adapter may send
deterministic catalog documents to the AmigaLab-namespaced `amigalab_catalog`
index. Credentials remain external to canonical metadata; Meilisearch
availability never affects offline SQLite search.

`meilisearch-sync`, `meilisearch-status`, `meilisearch-verify`, and
`meilisearch-clear --yes` are explicit operator commands. The configured
index must be `amigalab_`-namespaced and credentials are read only from the
external `AMIGALAB_MEILISEARCH_API_KEY` environment variable.
