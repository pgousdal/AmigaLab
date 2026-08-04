# systemd integration

The operations role installs only AmigaLab-namespaced units and only when
`amigalab_operations_enabled` is true. Timers are not enabled automatically.
Verification units use an absolute Python command, private temporary storage,
`ProtectSystem=strict`, and explicit metadata/runtime write paths. Collection
and media trees are not writable by scheduled verification.

