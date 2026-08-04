# Local catalog web interface

M2.23 provides a small standard-library WSGI application. It binds to
`127.0.0.1:8787` by default, serves only GET requests, and reads the derived
SQLite catalog. HTML is escaped, JSON is versioned informally under
`/api/v1`, and security headers are included. Missing catalogs produce a clear
offline rebuild hint; requests never trigger catalog builds or operations.

Enable the namespaced systemd service only after reviewing bind, port, and
read-only policy. File-body serving is disabled by default and is not
implemented in the initial interface.
