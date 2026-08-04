# Notifications

Scheduled runs record notification outcomes without storing credentials in
canonical metadata. A future adapter may write to the journal or a local
AmigaLab notification spool. Payloads should contain operation IDs, severity,
counts, and report references rather than secrets or unrestricted upstream
content.

