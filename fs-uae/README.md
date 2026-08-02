# FS-UAE profiles

The A500 and A1200 profiles require ROMs and Workbench media that you are
licensed to use. Keep ROMs in `/srv/amigalab/kickstarts` and configure local
Workbench volumes under `/srv/amigalab/workbench/A500` or `A1200`. The profile
files intentionally contain placeholder media paths and no ROMs.

Build a test executable on Linux, copy it to `/srv/amigalab/shared`, then launch
the appropriate profile with `fs-uae fs-uae/profiles/A1200.fs-uae`. That shared
directory is mounted as a second hard drive by both profiles. See
[profiles](profiles/README.md) for the expected media configuration.
