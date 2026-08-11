# AmigaLab

### A reproducible daily Amiga workstation, development/test lab, and preservation museum built on a Debian host

> Debian is the infrastructure underneath. The Amiga is the computer the user experiences.

AmigaLab uses Infrastructure as Code to turn a supported Debian machine into a
daily-use Amiga environment. Debian, Ansible, FS-UAE, containers, cross-tools,
and catalog services provide the recoverable foundation; normal use should feel
like powering on an Amiga rather than administering a Linux server.

The project has three complementary roles:

- a primary, persistent daily Amiga workstation;
- a native and cross-development lab with a local test matrix; and
- an offline-first software and documentation museum backed by preservation-grade storage.

M2 completed the preservation platform in v0.2.0. M3 is the planned workstation,
development/test, and museum milestone. See the [canonical M3 roadmap](docs/m3-roadmap.md)
for scope, dependencies, risks, and acceptance criteria. Most daily-workstation
features described there are not implemented yet.

## Project boundaries

- AmigaLab is a BBS **client** workstation. BBS hosting belongs to a separate
  Multi-BBS machine/project and is not part of M3.
- OpenVN integration is currently out of scope. It is not an M3 dependency,
  example project, CI target, or architectural requirement.
- Kickstart ROMs, Workbench/AmigaOS media, commercial software, proprietary
  SDKs, and other restricted assets are supplied lawfully by the operator.
  AmigaLab never commits, downloads, redistributes, or silently provisions them.
- Repository-owned configuration and metadata are reproducible; user assets,
  persistent Amiga disks, personal data, and preserved content must be restored
  from lawful inputs and backups. “Reproducible” does not mean those bytes are
  available from this repository.

## Current state

M2 provides the stable foundation that M3 will reuse:

- immutable preservation collections and separate canonical metadata;
- four-hash file records, provenance, verification, reconciliation, and
  auditable recovery;
- separately reviewed acquisition and import plans with resumable execution;
- Internet Archive metadata inspection and controlled HTTPS acquisition;
- deterministic SQLite/FTS5 cataloging, a localhost-only read-only catalog UI,
  and optional Meilisearch acceleration;
- opt-in scheduled operations that never approve destructive or
  preservation-changing actions;
- Debian/Ansible storage and development foundations;
- operator-installed cross-toolchain helpers; and
- native FS-UAE packages plus two placeholder A500/A1200 test profiles.

The current emulator profiles are not yet an appliance or a canonical daily
driver. They require operator-supplied licensed media and deliberate local
configuration. A600, A3000, and A4000-class profiles are roadmap candidates,
not current repository features.

## Architecture

```text
User experience:     daily Amiga | compatible/test profiles | museum
                           |
M3 runtime:          appliance session, profile launcher, safe bridges
                           |
Debian services:     FS-UAE, systemd, networking, build tools, optional containers
                           |
M2 foundation:       preserved objects + canonical metadata -> rebuildable views
```

The preservation and workstation planes meet only through explicit read-only
library exports or writable working copies. Preserved originals are never used
as emulator scratch disks, game save locations, build trees, or mutable shared
drives. See [architecture](docs/architecture.md), the
[preservation model](docs/preservation-model.md), and the
[M2 completion architecture](docs/m2.24-architecture.md).

## Repository layout

```text
ansible/       Debian host configuration and namespaced services
docker/        Optional Gitea, Meilisearch, Caddy, and Homepage services
docs/          Architecture, operations, preservation, and roadmap documents
examples/      Amiga cross-development examples
fs-uae/        Current placeholder emulator test profiles and guidance
metadata/      Repository examples/placeholders; live metadata is under /srv
scripts/       Preservation, catalog, recovery, and workstation helpers
tests/         Python test suite for the M2 preservation platform
toolchains/    Toolchain installation helpers and legal-input guidance
```

## Installation

On a supported Debian installation, clone the repository and run:

```sh
make install
```

The bootstrap installs Ansible and applies the workstation playbook. It creates
the `/srv/amigalab` hierarchy and installs the current host foundations; it does
not install licensed Amiga assets or complete M3 appliance configuration. See
the [installation guide](docs/installation.md).

Optional containers require Docker Compose v2 and a local environment file:

```sh
cp docker/.env.example docker/.env
# Set a strong Meilisearch key and review bindings.
make docker-up
```

Do not expose services beyond trusted interfaces without reviewing their
authentication, ports, and content policy.

## Storage model

Live state is namespaced under `/srv/amigalab`. M2 currently creates collection
roots such as `aminet`, `fish`, `docs`, `adf`, and `hdf`, separate metadata,
original-media storage, staging, build, backup, and shared directories. The M3
roadmap refines these into four explicit trust zones:

1. immutable preservation content;
2. canonical museum/preservation metadata and rebuildable indexes;
3. generated read-only Amiga-visible library exports; and
4. mutable workstation, project, staging, save, and runtime state.

Until that boundary is implemented, treat `/srv/amigalab/shared` as a mutable
development exchange only, never as preservation storage.

## Development today

Ansible installs host build prerequisites and versioned helpers for GCC, VBCC,
VASM, and VLINK. Toolchains and SDK inputs still require deliberate,
license-aware installation. The baseline flow is:

```text
source -> host cross-build -> /srv/amigalab/shared -> FS-UAE profile -> human test
```

Compilation inside the emulated Amiga is allowed and is an M3 workflow goal;
it is not required. Current scripts can prove a cross-build succeeded and can
launch FS-UAE, but they do not claim automated functional verification. See
[development](docs/development.md) and [toolchains](toolchains/README.md).

## Preservation guarantees

- Original collection paths and bytes remain immutable.
- AmigaLab metadata is additive and stored outside preserved collections.
- SQLite, Meilisearch, thumbnails, and web views are derived and rebuildable.
- Plans require separate review and approval before acquisition, import, or
  repair execution.
- Interrupted operations retain auditable state and resume conservatively.
- Catalog requests do not execute files or mutate the archive.
- Restricted content is non-redistributable by default.

## Documentation

- [M3 roadmap](docs/m3-roadmap.md)
- [Milestones](docs/milestones.md)
- [Architecture](docs/architecture.md)
- [Installation](docs/installation.md)
- [Development](docs/development.md)
- [Archive framework](docs/archive.md)
- [Preservation model](docs/preservation-model.md)
- [Licensing and export policy](docs/licensing.md)
- [M2 v0.2.0 release notes](docs/releases/v0.2.0.md)

## License

MIT License. Copyright © 2026.

*Preserving the past with the tools of the future.*
