# Architecture

AmigaLab separates reproducible host setup, optional services, and preserved
data. Ansible configures a Debian workstation and creates `/srv/amigalab`.
Docker Compose provides Gitea, Meilisearch, Caddy, and Homepage with named
volumes. FS-UAE runs natively and uses user-supplied ROMs and media from storage.

No copyrighted Amiga ROM, Workbench, or SDK material is included, fetched, or
configured automatically. This makes the infrastructure shareable while keeping
the workstation operator responsible for legal media and SDK inputs.
