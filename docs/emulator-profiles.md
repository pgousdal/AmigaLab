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

## Boot-to-Amiga host integration (M3.0.3)

M3.0.3 provides an explicitly selected boot appliance without making FS-UAE a
boot or administration dependency:

```text
Debian multi-user boot + normal gettys
  -> LightDM on its graphical seat
  -> local autologin of amigalab-appliance only
  -> AmigaLab X11 session
  -> systemd user unit (Restart=no)
  -> amigalab.py appliance-run
  -> M3.0.2 preflight/session supervisor
  -> /usr/bin/fs-uae, fullscreen as declared by the profile
```

LightDM/X11 establishes display and PAM/audio session ownership without a
desktop environment and matches FS-UAE's Debian graphical environment. `xterm`
is the only post-session UI. A systemd user unit owns stop and child lifecycle;
its fixed command accepts no profile-supplied command. `Restart=no`, no timer,
and no delay mean a failure is attempted once. The X session then remains at a
recovery terminal, preventing display-manager relogin loops.

The locked `amigalab-appliance` account has no sudo rights or usable password.
It receives only `audio`, `video`, and `input` for local display, sound, and
controllers. FS-UAE never runs as root. Local-seat autologin does not change
remote authentication, and no SSH setting is read or edited. `ProtectHome=true`
means appliance assets should live below `/srv/amigalab`, not a personal home.

### Configure, preview, enable, and disable

Create the ignored asset inventory first. The tracked examples contain no
usable ROM and are not daily-driver profiles. Use absolute inventory paths for
appliance mode because Ansible deploys the inventory from the clone to `/etc`;
the preview rejects relative paths whose meaning would change.

```sh
cp config/assets.example.json config/assets.local.json
# edit with lawful local paths and hashes
python3 scripts/amigalab.py appliance-check PROFILE_ID --json
python3 scripts/amigalab.py appliance-enable PROFILE_ID
make ansible
```

`appliance-enable` refuses a missing profile, invalid assets/trust zones, a
non-fullscreen profile, or unavailable FS-UAE. It atomically creates ignored
`config/appliance.local.json`; it does not mutate `/etc` or systemd. Ansible is
the explicit reconciliation boundary. It copies intent to
`/etc/amigalab/appliance.json`, the inventory to `/etc/amigalab/assets.json`
mode 0640, fixed code to `/opt/amigalab`, and provisions the writable runtime
at `/var/lib/amigalab-appliance/runtime`. Repeated runs are idempotent.

Read-only inspection is available before or after reconciliation:

```sh
python3 scripts/amigalab.py appliance-status
python3 scripts/amigalab.py appliance-check --json
python3 scripts/amigalab.py session-status --runtime-root /var/lib/amigalab-appliance/runtime
```

Disable without editing generated host files:

```sh
python3 scripts/amigalab.py appliance-disable
make ansible
```

This removes the AmigaLab LightDM autologin drop-in and disables its managed
boot service. Diagnostic runtime state and the locked account remain available.

### Boot, exit, failure, and stopping

After normal multi-user host startup, LightDM creates X11. The fixed session
imports only `DISPLAY` and `XAUTHORITY` into its user manager and starts
`amigalab-appliance.service`. The CLI reloads the selected profile, validates
inventory paths, hashes and zones, checks FS-UAE, creates isolated metadata,
and launches it. Normal quit, non-zero exit, missing display, manual stop,
invalid configuration, missing ROM/inventory, hash failure, and trust failure
all return to or leave the recovery terminal. An unlocked stale lock is safely
replaced by the existing supervisor. There is no shutdown or reboot action.

From another administrator login, stop the running unit with:

```sh
sudo -u amigalab-appliance XDG_RUNTIME_DIR=/run/user/$(id -u amigalab-appliance) \
  systemctl --user stop amigalab-appliance.service
```

The supervisor asks FS-UAE to terminate, waits five seconds, then escalates
only for its child. systemd uses a ten-second stop timeout and control-group
scope.

### Emergency recovery

If FS-UAE fails during automatic startup:

1. Press Ctrl-Alt-F2 (or F3) and log in with a normal Debian administrator.
   AmigaLab never disables gettys.
2. Alternatively use independently configured SSH. Appliance mode neither
   configures nor weakens it.
3. Inspect `journalctl _UID=$(id -u amigalab-appliance)` and the user unit from
   the appliance account context.
4. Run `session-status` with the host runtime path above, followed by
   `session-show SESSION_ID --runtime-root /var/lib/amigalab-appliance/runtime`.
   Emulator output is in the reported `logs/fs-uae.log`.
5. Run `appliance-disable` in the repository and `make ansible` if automatic
   entry should stay off.
6. Correct the profile/assets, rerun `appliance-check`, then enable and
   reconcile again.

Debian's normal non-graphical recovery target is also independent of X. Root is
never autologged, TTYs remain enabled, and FS-UAE is not required for an admin
login. M3.0.3 does not certify a daily-driver profile, install AmigaOS, power
off after exit, add networking, or add museum/game integration; those remain
later M3 work.
