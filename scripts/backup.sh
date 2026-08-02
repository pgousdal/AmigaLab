#!/usr/bin/env bash
set -euo pipefail

storage_root="${AMIGALAB_STORAGE_ROOT:-/srv/amigalab}"
backup_directory="$storage_root/backups"

if [[ ! -d "$backup_directory" ]]; then
  printf 'Backup directory does not exist: %s\nRun the Ansible playbook first.\n' "$backup_directory" >&2
  exit 1
fi

printf 'Backup workflow placeholder. No archive has been created.\n'
printf 'Future backups will target: %s\n' "$backup_directory"
printf 'Plan to include configuration, repositories, and selected Docker volumes.\n'
