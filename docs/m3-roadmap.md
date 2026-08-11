# M3 — Daily Amiga Workstation, Development Lab & Museum

## Intent

This is the canonical plan for the milestone after the completed M2
preservation platform. M3 turns one Debian host into a practical daily Amiga
without weakening M2's preservation, provenance, recovery, or approval
boundaries.

> Debian is the infrastructure underneath. The Amiga is the computer the user experiences.

M3 is complete only when AmigaLab can serve as a daily Amiga workstation, an
Amiga development/test lab, and a preservation museum. Debian administration
remains available through a deliberate recovery path, but it must not dominate
normal startup or use.

This document defines outcomes, not fixed machine specifications. CPU, RAM,
chipset, Kickstart, AmigaOS, RTG, audio, and filesystem choices must be tested
and recorded before a profile becomes canonical. The repository must never
invent compatibility claims or assume an operator owns a particular AmigaOS
release.

## Repository audit at the M2 boundary

### Foundations M3 can reuse

| Existing capability | M3 use |
| --- | --- |
| Debian playbook and namespaced `/srv/amigalab`, `/opt/amigalab`, and `/etc/amigalab` ownership | Appliance and workstation configuration without a second provisioning system |
| Native FS-UAE installation and placeholder A500/A1200 profiles | Emulator baseline and initial profile-validation fixtures |
| GCC/VBCC/VASM/VLINK helpers, shell environment, build example, and launch script | Cross-development pipeline foundation |
| Immutable collections, original-media store, four-hash records, provenance, and verification | Authoritative museum objects and launch-source custody |
| Plans, approvals, durable transactions, conflicts, recovery, and audit reports | Safe creation of explicit derivatives and working copies |
| External-source inspection and bounded, approved, resumable acquisition | Controlled collection growth; never a runtime dependency |
| Deterministic catalog documents, SQLite FTS5, read-only local web UI, optional Meilisearch | Museum discovery and later Amiga-facing read-only views |
| Disabled-by-default operations, localhost defaults, retention plans, and verification timers | Conservative appliance services and maintenance model |
| Coexistence contract and namespaced locks/ports | Isolation from other retro-computing projects on the host |

### Current gaps and misleading assumptions

- Ansible installs FS-UAE but does not own a graphical session, autostart,
  fullscreen lifecycle, clean shutdown, input/audio/display policy, or a host
  recovery escape.
- There is no canonical daily-driver profile. The tracked A500 and A1200 files
  are placeholder test profiles with local licensed-media paths, not validated
  complete systems. No tracked A600, A3000, or A4000 profile exists.
- `/srv/amigalab/shared` is a convenient mutable exchange, but M2 does not yet
  define separate workstation disks, game saves, CI artifacts, generated
  library views, or per-profile runtime state.
- Toolchain helpers exist, but the GCC workflow is documented rather than
  automated and VBCC/SDK inputs can have redistribution restrictions. The
  example proves build output exists; emulator launch is not a functional test.
- `scripts/backup.sh` is a placeholder. Current claims of complete workstation
  reconstruction therefore depend on operator-managed archives and backups.
- The catalog models preservation-centric entities and offers read-only views;
  it is not yet the richer museum relationship model or a safe launcher.
- M2 has no Amiga-side TCP/IP stack, client-software policy, legacy-protocol
  gateway, or threat boundary.
- The earlier README overstated complete mirrors, emulator model coverage,
  AmigaOS support, hands-free setup, and host services. Those are not evidence
  of implemented M3 capabilities.

## Non-negotiable boundaries

### Proprietary and restricted assets

Kickstart ROMs, Workbench/AmigaOS installation media and installed systems,
commercial games/applications, WHDLoad game content, proprietary NDK/SDK files,
and keys are operator-supplied. They must never be committed, fetched by
default, embedded in images, copied into logs/test fixtures, or redistributed.

Repository configuration refers to logical asset requirements. A local,
ignored inventory may record operator-selected paths and hashes. Validation may
identify a missing or mismatched asset, but must not search uncontrolled
locations, infer a license, or fetch a replacement. Backups containing
restricted assets remain local, access-controlled, and excluded from Git.

Free/open replacements may be supported as explicit profiles when technically
suitable. Their availability must not silently change a profile documented for
proprietary firmware or software.

### Four storage and trust zones

```text
preservation originals (immutable, authoritative)
        |
        +--> canonical metadata --> rebuildable indexes/views
        |
        +--> explicit derivation/export --> Amiga-visible read-only library
                                            |
                                            +--> explicit working copy
                                                  (mutable workspace/runtime)
```

1. **Preservation content** retains original bytes and hierarchy. It is never
   directly writable from an emulated Amiga.
2. **Canonical metadata** records custody, relationships, and decisions.
   Catalog databases, thumbnails, caches, and UI views are rebuildable.
3. **Amiga-visible library data** is generated, attributable, read-only where
   the emulator/host boundary permits, and safe to recreate.
4. **Mutable state** includes system disks, user data, source checkouts, build
   trees, staging, saves, configuration overlays, logs, and snapshots. It is
   backed up by retention class and is never treated as an original merely
   because it originated in the archive.

An emulator profile must declare every mounted path and its zone. A launch must
fail closed when an expected read-only boundary cannot be enforced.

### Networking and legacy security

AmigaLab is a BBS client workstation only. BBS hosting belongs on the separate
Multi-BBS machine/project. No M3 service listens as a public BBS.

Historic Amiga clients, TCP/IP stacks, Telnet, FTP, IRC, and web software may
lack encryption, certificate validation, memory safety, and modern
authentication support. Therefore:

- legacy traffic uses a dedicated, least-privilege path with a documented host
  firewall and exposure;
- credentials used by legacy software are unique and low-value; modern primary
  credentials and secrets never enter the Amiga environment;
- Telnet and FTP are labeled cleartext, not described as secure Internet access;
- host proxies/gateways are optional, narrowly scoped, auditable, disabled by
  default, and never imply nonexistent end-to-end security;
- untrusted downloads land in mutable quarantine/staging, never directly in a
  preserved collection, system disk, or host executable path;
- inbound host services bind locally or to an explicitly selected trusted
  interface and require review before exposure; and
- normal offline use, archive verification, and the daily desktop do not
  depend on Internet availability.

### Emulator and appliance safety

FS-UAE configuration is repository-generated from a declarative profile plus a
local asset inventory. Generated files and runtime state are not authoritative.
Profiles record all behavior that affects compatibility: model/chipset, CPU,
memory, ROM requirement, storage, filesystem, display, RTG, audio, input,
networking, clock behavior, and integration features.

Automatic startup is gated on preflight checks. Failure presents a useful local
recovery screen or console instead of a restart loop. A documented host escape
works without the guest, remote administration remains operator-controlled,
logs are bounded and contain no media bytes or credentials, and shutdown
flushes writable guest storage before powering off the host. Save states are
convenience data, not backups or preservation evidence.

## Structure and dependencies

The proposed M3.0–M3.8 structure is retained because each unit has a distinct
operator outcome. Its order is refined: M3.0 establishes boundaries; M3.1 is
the daily-driver product; M3.2 and M3.3 add user workflows; M3.4 enables M3.5;
M3.6 builds on M2 metadata and validated profiles; M3.7 creates the controlled
archive/guest bridge; M3.8 closes recovery. M3.6 metadata work may proceed
beside M3.2–M3.5, but launch integration waits for M3.0, profile contracts from
M3.3/M3.5, and M3.7 export controls.

```text
M2 complete
   |
 M3.0 appliance/profile/storage boundary
   |
 M3.1 canonical daily driver
   +------> M3.2 networking and BBS clients
   +------> M3.3 gaming profiles
   +------> M3.4 native and cross-development ---> M3.5 local CI matrix
   |
   +------> M3.7 archive-to-Amiga bridge <------ M3.6 museum model/views
                                                       |
                                  validated profile launch integration

M3.8 backup, restore, and polish closes all preceding state classes
```

## M3.0 — Amiga Appliance Foundation

Define the host/runtime contract before choosing the daily Amiga. Add
declarative profile ownership, local asset references, storage-zone mounts,
preflight, a session lifecycle, fullscreen/display/audio/input/removable-media
policy, clean shutdown, bounded logs, failure behavior, and documented local
and remote recovery. All host mutations remain Ansible-owned and idempotent.

Acceptance criteria:

- a versioned profile schema distinguishes repository configuration, local
  restricted-asset references, generated configuration, and mutable runtime state;
- preflight validates required assets by operator-recorded identity, mount
  zones, writable space, display/audio/input prerequisites, and required
  services without modifying preserved content;
- Ansible can configure and disable the appliance session idempotently, with
  autostart opt-in until recovery has been verified;
- one redistributable fixture profile exercises generation and validation in
  automated tests without proprietary bytes;
- a session can start FS-UAE fullscreen and exit cleanly without powering off
  the host; unexpected exit does not loop forever;
- input ownership, removable media, logs/retention, service ordering, and
  offline behavior are documented and tested where practical; and
- at least one local host escape and one independently configured
  administrative recovery path are demonstrated and documented.

M3.0.1 through M3.0.4 implement this foundation. Automated checks cover
configuration, preflight, prerequisites, policy, and session evidence, but
hardware acceptance requires [M3.0 appliance hardware
qualification](appliance-qualification.md). Current status: **M3.0
implementation complete; hardware qualification pending**. M3.0 is not
complete until a real host records the required human passes; independently
configured SSH and an absent controller may be `SKIP`.

## M3.1 — Daily Driver Amiga

Create one named canonical primary workstation profile. Select its model, CPU,
RAM, chipset, ROM/AmigaOS requirement, RTG, audio, networking, filesystems, and
integration features from recorded compatibility and usability evidence. Other
profiles remain separate and cannot silently alter its system disk.

Acceptance criteria:

- an architecture decision records the configuration, alternatives, legal
  inputs, compatibility rationale, and known limitations;
- a fresh lawful installation can create or restore the persistent system disk
  without committing or downloading proprietary content;
- normal boot reaches the Amiga desktop fullscreen with sound, chosen display,
  keyboard/mouse, deterministic storage, and documented removable media;
- reboot, guest/host shutdown, emulator crash, and disk-full behavior have
  tested safe outcomes without writes to preservation storage;
- shared folders, clipboard, clock, and other integration are individually
  configurable and enabled only with documented benefit; and
- system disk, user data, configuration, and runtime state have tested backup
  and restore procedures with recovery-point expectations.

## M3.2 — Networking, Internet & BBS Clients

Enable authentic Amiga-side TCP/IP and applications for BBS access, Telnet,
IRC, FTP, web use, and file transfer where compatible. Prefer actual Amiga
clients; add a host bridge only for a documented modern protocol gap.

Acceptance criteria:

- network topology, DNS, addressing, firewall boundary, and offline mode are
  reproducibly configured and documented;
- at least one Amiga TCP/IP stack and one BBS/Telnet client, installed from
  lawful operator inputs, make an outbound test connection;
- supported IRC, FTP, web, and transfer workflows state tested capability,
  limitations, and whether traffic is cleartext or bridged;
- optional gateways are disabled by default, least-privilege, bounded, logged
  without secrets, and removable without breaking offline use;
- untrusted downloads enter mutable staging/quarantine; and
- no BBS server or public inbound legacy service is installed or enabled.

## M3.3 — Gaming & WHDLoad

Keep games and machine-specific compatibility outside the canonical daily
driver. Support lawful WHDLoad, ADF, and applicable CD workflows using immutable
source media plus explicit writable saves/overlays.

Acceptance criteria:

- gaming profiles declare machine/ROM requirements and tested reasons for CPU,
  memory, chipset, display scaling, latency, audio, and input choices;
- joystick/gamepad mapping and switching between daily and gaming profiles work
  without host administration;
- ADF, WHDLoad, and supported CD flows never write to preserved originals;
- saves, overlays, screenshots, configuration, and optional save states have
  explicit mutable locations and backup/retention policies;
- cold-boot and clean-exit tests pass for each profile, while compatibility
  claims require separate recorded human verification; and
- restricted game content and WHDLoad assets are neither fetched nor committed.

## M3.4 — Native & Cross Development

Support both development inside the Amiga and Linux-hosted cross-development.
Reuse the existing toolchain helpers and example. Standardize this flow:

```text
source -> build -> stage -> launch on target profile -> inspect/test -> iterate
```

Acceptance criteria:

- compiler/assembler/linker recipes pin identifiable versions and verify
  downloads; licenses and operator-supplied NDK/SDK boundaries are explicit;
- at least one example builds reproducibly with the supported host toolchain
  from a clean documented environment;
- source, build, stage, guest-visible output, and evidence use distinct paths,
  and stale artifacts cannot be mistaken for a new build;
- one command builds, stages, and launches a selected target, reporting each
  phase separately;
- a documented native-Amiga edit/build/run workflow works on a mutable project
  copy without making native compilation mandatory; and
- Git/editor integration does not expose host credentials or make the guest
  system disk the only copy of source.

## M3.5 — Local Amiga CI & Test Matrix

Provide a local reproducible runner across supported compatibility classes.
A500-, A600-, A1200-, A3000-, and A4000-class targets are candidates, not a
promise. A target enters the matrix only with a justified validated
configuration and lawful local assets.

Acceptance criteria:

- a machine-readable matrix records each target's purpose, profile identity,
  required assets, timeout, test capability, and support status;
- the runner is non-interactive where claimed, uses isolated writable state,
  bounds resources/logs, and cannot write preserved originals;
- reports separately identify build success, emulator launch success, automated
  smoke-test success, and pending/passed/failed human verification;
- at least two materially different target classes execute the same example
  through build and launch, and one has a deterministic smoke test beyond startup;
- unavailable proprietary inputs produce a clear skip, never a false pass or
  automatic download; and
- reports work locally offline through a stable interface suitable for later
  Git-host integration without requiring a cloud service.

## M3.6 — Museum Experience

Extend the M2 catalog into a preservation-first museum. Model software,
releases, media, machines, people/organizations, documentation, screenshots,
source, preserved artifacts, relationships, and compatible validated profiles.
Canonical records remain authoritative; views and thumbnails remain derived.

Acceptance criteria:

- versioned canonical schemas represent entities, provenance, licensing/access
  policy, relationships, and uncertainty without rewriting M2 records;
- migrations/backfills are deterministic, additive, auditable, resumable where
  necessary, and compatible with the v0.2.0 preservation model;
- SQLite search and local read-only views rebuild entirely from canonical
  metadata and preserved-object references while offline;
- representative entries navigate software-to-release-to-media-to-machine and
  documentation/source/creator relationships, including unknown values;
- restricted bodies and metadata follow access policy and derived thumbnails
  never become preservation authorities; and
- launch resolves only an allowlisted record and validated profile through the
  M3 launcher—never an arbitrary path or command—and requires explicit action.

## M3.7 — Archive ↔ Amiga Integration

Expose useful Aminet, Fish, documentation, ADF/HDF, source, SDK, and other local
holdings through generated library views and explicit working copies. Never
mount canonical collections writable or treat them as guest workspaces.

Acceptance criteria:

- every export records its canonical source identity, policy, transformation,
  output hash/path, generator version, and read-only/working-copy status;
- selection enforces license/access policy and blocks restricted redistribution
  unless an explicit local-use policy permits it;
- the Amiga browses at least one read-only software collection and one
  documentation collection while the host is offline;
- attempts to alter a read-only view cannot change preserved objects or
  canonical metadata and are detected by verification;
- creating a writable copy is explicit and attributable, and changes never flow
  back automatically; and
- stale views rebuild deterministically and interrupted exports resume or fail
  without being presented as complete.

## M3.8 — Backup, Restore & Workstation Polish

Close the appliance lifecycle across configuration, system disks, user data,
projects, emulator state, museum metadata, preserved content, and derived data.

Acceptance criteria:

- a versioned inventory classifies each persistent path as repository-owned,
  proprietary input, canonical preservation/metadata, mutable user state,
  credential, cache/derived state, or disposable runtime state;
- policy defines inclusion, consistency/quiescing, encryption, retention,
  integrity verification, and recovery objectives for each non-disposable class;
- restore drills recover the daily driver and a development project and verify
  archive/metadata integrity afterward;
- derived catalog/search/thumbnail/library state is rebuilt and verified rather
  than relied upon as the sole backup;
- fresh supported Debian plus this repository, lawful operator assets, and
  backups reconstructs a usable workstation through a tested procedure; and
- final boot, shutdown, controller, display/audio, offline, failure-recovery,
  and host-escape checks pass as an operator-facing runbook.

## Smallest safe next implementation slice

Implement only the first contract slice of M3.0:

1. define a versioned declarative emulator-profile schema with mount-zone and
   asset-requirement fields;
2. add an ignored local asset-inventory example containing paths and expected
   hashes but no proprietary bytes;
3. implement a read-only preflight/renderer that rejects missing assets,
   writable preservation mounts, path escapes, and undeclared mutable paths;
4. exercise it with a fully redistributable synthetic fixture and automated
   tests; and
5. document the generated/runtime layout and manual launch command.

Do not yet enable autologin, autostart, host shutdown, network bridges, or
migrate the placeholder profiles. Those depend on the validated contract and
hardware/session testing. This slice creates enforceable boundaries while
remaining testable without copyrighted assets or a graphical host.

## Explicit deferrals

- BBS hosting belongs to the separate Multi-BBS machine/project. AmigaLab runs
  outbound Amiga BBS clients only.
- OpenVN is out of scope and is not an example, test target, dependency, or
  acceptance gate for M3.
- Cloud CI and any particular Git host are optional future integrations; local
  operation is authoritative.
- Unrestricted catalog-driven file execution is prohibited.
- Automatic acquisition, approval, redistribution, or installation of
  proprietary Amiga assets is prohibited.
- Exact daily-driver and compatibility-profile specifications await measured
  compatibility work and an architecture decision.
