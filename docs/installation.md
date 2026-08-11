# Installation

On a fresh Debian workstation, clone this repository and run:

```sh
make install
```

The bootstrap script verifies Debian, installs Ansible, then applies the local
playbook with elevated privileges. It installs baseline development packages,
FS-UAE, and creates `/srv/amigalab` storage directories.

This installs the current M2 host foundation, not a finished M3 appliance or
daily-driver Amiga. Licensed Kickstart, Workbench/AmigaOS, commercial software,
and proprietary SDK assets must be supplied and configured deliberately by the
operator; the repository never downloads or redistributes them. The current
FS-UAE profiles are placeholders. Follow the [M3 roadmap](m3-roadmap.md) rather
than enabling unattended graphical startup from them.

M3.0.1 supports a manual-only profile preflight and launch foundation. It does
not alter login or boot. To configure the ignored local asset inventory and run
preflight, follow [canonical emulator profiles](emulator-profiles.md).

To enable the Visual Studio Code repository, set `vscode_repository_enabled:
true` in an inventory-specific variable file. Set `vscode_install_package: true`
as well if Ansible should install Code.

Boot-to-Amiga remains absent from an ordinary install. To opt in, first create
the local inventories and pass the appliance check described in
[appliance host integration](emulator-profiles.md#boot-to-amiga-host-integration-m303),
then run the normal Ansible playbook. The playbook installs LightDM/X11 and the
dedicated account only when `config/appliance.local.json` says `enabled: true`.

For containers, copy `docker/.env.example` to `docker/.env`, replace the
Meilisearch key, and run `make docker-up`. Review and set public hostnames and
ports before exposing services beyond the local machine.
