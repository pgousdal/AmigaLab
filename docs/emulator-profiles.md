# Canonical profiles and appliance sessions (M3.0.2)

M3.0.1 provides a deliberately small, executable FS-UAE launch contract. It
can validate, report, render, and manually launch a profile. It does not provide
a daily-driver installation, appliance session, autostart, networking, WHDLoad,
museum launching, host shutdown, or automatic migration of legacy profiles.

## Canonical and local state

Tracked JSON profiles live in `profiles/`. `profiles/schema-v1.json` documents
version 1; `profiles/example-a1200.json` is a contract example, not a tested
production configuration. Unknown fields fail validation, so profiles cannot
inject arbitrary FS-UAE options. Stable lower-case IDs and sorted renderer keys
make the output repeatable.

Kickstart, Workbench/AmigaOS, commercial media, and other restricted assets are
always lawfully supplied by the operator. AmigaLab neither includes nor
downloads them. Profiles refer only to logical IDs. Copy
`config/assets.example.json` to the Git-ignored `config/assets.local.json` and
replace each example path and SHA-256 value. Relative inventory paths resolve
against the inventory file's directory; absolute paths and `~` are accepted.
No directory search or environment-variable expansion occurs. Duplicate IDs,
missing files, and declared hash mismatches are failures.

Generated files are non-authoritative and Git-ignored:

- `runtime/profiles/config/<profile-id>.fs-uae` — rendered configuration;
- `runtime/profiles/state/` — reserved per-profile runtime state; and
- `config/assets.local.json` — operator-local path and identity inventory.

The runtime root can be overridden explicitly on either command. Its profile
subdirectories are restricted to one stable relative component. Preflight is
read-only and does not create these paths.

## Trust zones and mounts

Every system disk, removable medium, directory, or HDF mount declares a trust
zone and a boolean `writable` intent. Its inventory record independently
classifies mountable assets. The declarations must match; an unknown or
ambiguous classification fails closed. Permissions are never downgraded.

| Trust zone | Writable emulator mount |
| --- | --- |
| `preservation-original` | forbidden |
| `canonical-derived` | forbidden |
| `amiga-library-export` | forbidden |
| `mutable-workstation-state` | explicitly permitted |

Preservation originals therefore cannot become writable runtime storage.
Library exports remain read-only; M3.0.1 has no approved writable-copy
mechanism. Mutable system disks, projects, and saves can be declared writable.
FS-UAE hard-drive read-only flags are emitted explicitly. Floppy write-through
is controlled by FS-UAE's global option, so mixed floppy write intents fail;
read-only floppy changes use overlays under the declared runtime state path.
CD media is read-only and a writable CD declaration fails as unsupported.

## Preflight and manual launch

From a fresh clone:

```sh
cp config/assets.example.json config/assets.local.json
# Edit only the local inventory with lawful asset paths and correct SHA-256 values.
python3 scripts/amigalab.py profile-preflight example-a1200
python3 scripts/amigalab.py profile-preflight example-a1200 --json
python3 scripts/amigalab.py profile-launch example-a1200 --dry-run
python3 scripts/amigalab.py profile-launch example-a1200
```

Preflight reports the profile identity, schema and machine, resolved assets,
existence/hash status, mounts and requested permissions, output paths, issues,
and whether launch is allowed. It exits 2 on failure. Manual launch repeats
preflight, writes the generated config only after success, and executes FS-UAE
with a subprocess argument array. `--dry-run` renders and prints that array but
does not execute the emulator. Launch exits 3 when FS-UAE is unavailable.

The example cannot launch unchanged: its inventory values are placeholders and
its profile is only a synthetic contract. A real manual launch requires FS-UAE,
a compatible lawful ROM, a lawful/mutable system disk if used, all declared
mount sources, correct optional hashes, and profile choices compatible with
those assets. Compatibility has not yet been certified by M3.1.

## Manual appliance sessions

M3.0.2 wraps the same profile, inventory, preflight, and renderer in a
supervised appliance session. It is deliberately started from a normal Debian
login and does not alter boot, autologin, a display manager, graphical session
ownership, networking, or host power control.

```sh
python3 scripts/amigalab.py session-launch example-a1200 --dry-run
python3 scripts/amigalab.py session-launch example-a1200
python3 scripts/amigalab.py session-status
python3 scripts/amigalab.py session-status --json
python3 scripts/amigalab.py session-show SESSION_ID
```

The canonical profile's matching `launch.mode` and `display.fullscreen` values
render `fullscreen = 1`; there is no appliance-only fullscreen switch. A
session dry run performs read-only preflight and prints the proposed paths and
argument array without creating state or starting FS-UAE. For M3.0.1
compatibility, `profile-launch --dry-run` still writes its deterministic legacy
render. Real `profile-launch` and `session-launch` share one supervisor.

### Lifecycle and runtime layout

Each real launch has a safe generated ID and isolated generated state:

```text
runtime/profiles/
├── appliance.lock
└── sessions/SESSION_ID/
    ├── state.json
    ├── config/PROFILE_ID.fs-uae
    ├── state/
    ├── logs/lifecycle.jsonl
    ├── logs/fs-uae.log
    ├── overlays/
    └── temp/
```

`state.json` schema version 1 moves only through `preparing → ready → running`
and then `exited`, `failed`, or `interrupted`. Invalid transitions fail. Atomic
replacement prevents partial JSON rewrites. The adjacent `preflight.json`
retains the launch decision. State records timestamps, child
PID only while running, the argument array, config/log locations, exit code,
reason, abnormal-exit flag, and cleanup status. It contains no asset bytes,
hashes, or guest content. Failed-session metadata and per-session logs survive
for diagnosis; M3.0.2 does not yet implement retention pruning.

Generated config, emulator state, overlays, logs, and temporary data remain in
the session. Runtime placement inside a mounted read-only preservation,
canonical-derived, or library-export directory is rejected before creation.
All `runtime/` content remains Git-ignored and non-authoritative.

### Supervision, locking, and recovery

FS-UAE is started directly with a subprocess argument array, never a shell.
Console output and errors go to the session emulator log, capped at 1 MiB. The supervisor waits
for that child, persists its exit code, and classifies zero, non-zero, and
interrupted exits. Ctrl-C or SIGTERM asks the child to terminate and waits up
to five seconds; only then does it kill that child and record the escalation.

An advisory `flock` permits one appliance supervisor per runtime root. Lock
metadata names the session and supervisor, but file existence alone is never
proof of activity. `session-status` reports `active`, `stale`, or `none`, plus
incomplete state and the most recent session. A later launch safely takes and
rewrites an unlocked stale lock; do not delete lock files as routine recovery.

Normal emulator exit returns to the launching Debian terminal. The standard
FS-UAE quit action remains the primary graphical escape. Ctrl-C in the launch
terminal is the controlled host escape. No login, TTY, SSH, or display-manager
configuration is changed, so another configured TTY (commonly Ctrl-Alt-F2/F3)
or an already available SSH session remains independent emergency recovery.
From there, run `session-status` and inspect the logs; this does not depend on
AmigaOS booting.

M3.0.2 does **not** provide boot-to-Amiga, autologin, automatic session startup,
automatic host poweroff, or a certified daily-driver Amiga profile. Emulator
console output also does not prove AmigaOS reached its desktop.
