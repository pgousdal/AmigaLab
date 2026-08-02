# Installation

On a fresh Debian workstation, clone this repository and run:

```sh
make install
```

The bootstrap script verifies Debian, installs Ansible, then applies the local
playbook with elevated privileges. It installs baseline development packages,
FS-UAE, and creates `/srv/amigalab` storage directories.

To enable the Visual Studio Code repository, set `vscode_repository_enabled:
true` in an inventory-specific variable file. Set `vscode_install_package: true`
as well if Ansible should install Code.

For containers, copy `docker/.env.example` to `docker/.env`, replace the
Meilisearch key, and run `make docker-up`. Review and set public hostnames and
ports before exposing services beyond the local machine.
