# M3.0 appliance hardware qualification

M3.0.4 adds read-only host diagnostics and the real-host acceptance procedure
for the complete M3.0 appliance stack. It does not install AmigaOS, configure
Amiga networking, expose archives, or claim that detected hardware worked in
the emulator.

Current status: **M3.0 implementation complete; hardware qualification
pending**. No real-host cold boot, display, audio, or input check is recorded by
this repository change.

## Diagnostic interface and status meanings

```sh
python3 scripts/amigalab.py appliance-qualify
python3 scripts/amigalab.py appliance-qualify --json
python3 /opt/amigalab/scripts/amigalab.py appliance-qualify \
  --config /etc/amigalab/appliance.json \
  --inventory /etc/amigalab/assets.json \
  --runtime-root /var/lib/amigalab-appliance/runtime \
  --fs-uae /usr/bin/fs-uae --json
```

Run inside the actual LightDM appliance session when its `DISPLAY` and
`XAUTHORITY` evidence is required; do not invent those values. The command
never creates files, opens devices, changes groups, starts services, mounts
media, or changes appliance intent. Its exit code is zero only when automated
checks have no `FAIL`.

- `PASS`: an automated prerequisite or policy check succeeded;
- `FAIL`: an automated prerequisite or safety check failed;
- `SKIP`: optional or inapplicable, including an absent controller;
- `HUMAN_REQUIRED`: the hardware-facing outcome must be observed by a person.

`automated_ready` never means hardware-qualified. `hardware_qualified` remains
false because a read-only probe cannot attest human results. Store reviewed
reports and notes under ignored `qualification-reports/`. The tracked contract
is [schema version 1](appliance-qualification-schema-v1.json). Alongside the
generated report, record operator, time, check ID, human `PASS`/`FAIL`/`SKIP`,
notes, and relevant session ID. Do not record secrets or proprietary bytes.

## Supported baseline and hardware policy

The baseline is one primary display, Debian LightDM with Xorg, the dedicated
`amigalab-appliance` local PAM session, no desktop or window manager, and
fullscreen FS-UAE. LightDM owns the display and authority; the session imports
`DISPLAY` and `XAUTHORITY`. FS-UAE exit leaves an `xterm` recovery console.
Useful resolution means the primary display is legible, fills as intended, and
keeps the expected aspect ratio. Exotic multi-monitor setups are outside M3.0.

FS-UAE sends audio through OpenAL. OpenAL may use PipeWire,
PulseAudio-compatible services, or ALSA on Debian, so diagnostics report the
detected host rather than selecting a backend. Audible Paula output remains a
human check. The locked appliance account receives only the existing `audio`,
`video`, and `input` supplementary groups, with no sudo or root execution.

Keyboard and mouse input remain owned by FS-UAE and X11; there is no custom
grabber. The FS-UAE F12 menu controls emulator interaction. Ctrl-Alt-F2/F3 is
the independent host recovery interaction, not an Amiga key combination.
Record capture/release and reserved shortcuts for the installed FS-UAE version.

Linux controller discovery records the kernel name, bus/vendor/product
identity, handlers, and readable nodes. Profiles must never name transient
`/dev/input/eventN` or `/dev/input/jsN` paths. FS-UAE accepts a device name for
`joystick_port_0`/`joystick_port_1`; newer releases document universal event
names. M3.0 retains automatic first-supported-controller selection. Add a
named port only after verifying the exact name with `fs-uae --list-joysticks`;
record replug and reboot behavior. See primary FS-UAE documentation for
[joystick port 1](https://fs-uae.net/docs/options/joystick-port-1/),
[input mapping](https://fs-uae.net/docs/input-mapping/), and
[audio](https://fs-uae.net/audio/).

Removable USB storage is host-only by default. Detection creates no guest
mount. Guest access requires an operator-chosen path in the ignored inventory
and an explicit canonical profile mount. Preservation originals and canonical
derived data remain read-only. Stage untrusted or mutable USB content in
mutable workstation state before Amiga access; automount must not bypass trust
zones or normal preservation import.

## Exact real-host procedure

1. Install or reconcile with `make ansible`; confirm normal Debian gettys and a
   normal administrator login remain available.
2. Configure lawful absolute asset paths and hashes in
   `config/assets.local.json`. Select a fullscreen canonical profile.
3. Run `profile-preflight PROFILE_ID --json`, `appliance-check PROFILE_ID
   --json`, and `appliance-qualify --json`; resolve every automated `FAIL`.
4. Run `appliance-enable PROFILE_ID`, reconcile, and retain the documented
   disable/reconcile command at the recovery login.
5. Power fully off, then cold boot. Confirm LightDM starts X11 and launches the
   selected profile automatically exactly once.
6. Confirm the primary display is useful, aspect-correct, and fullscreen;
   record resolution and limitations.
7. Produce known Paula audio and confirm it is audible on the intended output
   without permission errors.
8. Confirm ordinary Amiga keyboard input, F12 menu operation, and that
   Ctrl-Alt-F2 reaches Debian TTY2.
9. Return to X and confirm mouse movement, buttons, capture, and release.
10. If a controller exists, record `fs-uae --list-joysticks`, Linux identity,
    device access, directions/fire in Amiga, then replug and retest. Otherwise
    record optional/not-present `SKIP`.
11. Insert representative USB media. Confirm Linux detects it and Amiga does
    not unless the profile explicitly maps a controlled asset. Do not test with
    preservation originals.
12. Exit FS-UAE normally. Confirm the recovery console, session state `exited`,
    exit code zero, and no relaunch.
13. Relaunch once; from the independent admin login stop the user unit using
    the command in [appliance sessions](emulator-profiles.md#boot-exit-failure-and-stopping).
    Confirm `interrupted` state and no restart.
14. Confirm TTY recovery. If SSH was independently configured, test and record
    it; otherwise record `SKIP`.
15. Reboot and confirm one further automatic successful startup.
16. From recovery, disable/reconcile. Safely make one dependency unavailable,
    for example by temporarily changing an ignored inventory asset path. Do not
    alter preserved content and do not automate failure injection.
17. Re-enable/reconcile and reboot. Confirm preflight failure, no restart loop,
    usable TTY/recovery console, and coherent session/journal evidence.
18. Restore configuration, rerun preflight and qualification, reconcile,
    reboot, and repeat successful display/audio/input checks.

Only reviewed observations can become human `PASS`. Process startup alone
cannot pass display, audio, keyboard, mouse, or controller use. A controller
and SSH may be `SKIP`; cold boot, display, audio, keyboard/mouse, clean exit,
interruption, repeat boot, and safe failure recovery may not.
