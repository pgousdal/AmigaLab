# Optional Meilisearch

SQLite remains the default local search backend. An optional adapter may send
deterministic catalog documents to the AmigaLab-namespaced `amigalab_catalog`
index. Credentials remain external to canonical metadata; Meilisearch
availability never affects offline SQLite search.
