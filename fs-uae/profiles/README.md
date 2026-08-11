# Legacy FS-UAE placeholder profiles

`A500.fs-uae` and `A1200.fs-uae` mount `/srv/amigalab/shared` as a second hard
drive, making it a convenient destination for Linux-built executables. Replace
the `REPLACE_WITH_*` paths with ROM and Workbench media you are licensed to use.

These manually maintained files predate the M3 canonical profile contract. They
are retained as legacy examples, are not production-ready profiles, and are not
used by `profile-preflight` or `profile-launch`. Automatic migration is deferred.
New profiles belong in `profiles/` and generate runtime configuration; see
[`docs/emulator-profiles.md`](../../docs/emulator-profiles.md).

The A500 profile expects a Kickstart 1.3-compatible ROM; the A1200 profile
expects a Kickstart 3.1-compatible ROM. Configure a local Workbench installation
under `/srv/amigalab/workbench/A500` or `/srv/amigalab/workbench/A1200` as needed.
AmigaLab does not provide or download these copyrighted files.
