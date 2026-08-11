# Architecture

AmigaLab is a reproducible daily Amiga workstation, development/test lab, and
preservation museum built on a Debian host. Debian is the infrastructure layer;
the normal user-facing computer is the Amiga environment.

M2 supplies the completed preservation plane: original files and canonical
JSON/YAML metadata are authoritative; plans, approvals, provenance, recovery,
and verification are auditable; SQLite, Meilisearch, reports, and web views are
derived or read-only. M3 adds an appliance/runtime plane without replacing or
weakening that model.

```text
Amiga experience
  daily driver | compatibility/gaming | development/test | museum
                              |
managed runtime (M3)          | explicit, policy-checked bridges
                              |
Debian + Ansible + FS-UAE + optional local services
                              |
M2 preserved objects + canonical metadata + rebuildable views
```

All host-owned resources remain namespaced under `/srv/amigalab`,
`/opt/amigalab`, and `/etc/amigalab`. The emulator boundary must distinguish
immutable preservation content, canonical metadata/derived views, generated
read-only Amiga library exports, and mutable workstation/runtime state. No
emulated Amiga receives writable access to preserved originals.

FS-UAE currently runs natively and only placeholder A500/A1200 test profiles
are tracked. M3 will define a canonical daily driver and appliance session; it
must retain a deliberate local escape and independent administrative recovery
path even when normal boot hides Debian.

M3.0.1 defines the versioned canonical profile, ignored logical-asset
inventory, explicit trust-zone mount checks, deterministic FS-UAE rendering,
read-only preflight, and manual launch foundation. M3.0.2 adds isolated
generated sessions, atomic lifecycle state, single-session locking, child
process supervision, diagnostics, and independent host recovery while launch
remains manual. M3.0.3 adds opt-in boot integration: LightDM owns one X11 seat,
logs in only a locked unprivileged appliance account, and a systemd user unit
invokes the same supervisor. It does not replace Debian boot, gettys, PAM
administration, or SSH. See [canonical profiles and appliance sessions](emulator-profiles.md).

Kickstart ROMs, Workbench/AmigaOS media, commercial software, proprietary SDKs,
and other restricted assets are supplied lawfully by the operator. They are not
included, fetched, or configured automatically. Repository-owned declarations
may refer to local assets through an ignored inventory and verify their identity.

Optional containers provide Gitea, Meilisearch, Caddy, and Homepage. The M2
catalog web service is localhost-only and read-only by default. Legacy Amiga
networking and any compatibility gateways introduced by M3 must remain optional,
least-privilege, and explicit about cleartext and obsolete-protocol risks.

See the [M3 roadmap](m3-roadmap.md), [preservation model](preservation-model.md),
and [coexistence contract](coexistence.md).
