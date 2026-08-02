#!/usr/bin/env bash
set -euo pipefail

storage_root="${AMIGALAB_STORAGE_ROOT:-/srv/amigalab}"
required_commands=(git gcc make cmake python3 pip3 fs-uae ansible-playbook docker)
required_directories=(aminet whdload adf hdf kickstarts workbench ndk docs magazines fish demos source builds backups shared)
failed=0

for command_name in "${required_commands[@]}"; do
  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'ok: command %s\n' "$command_name"
  else
    printf 'missing: command %s\n' "$command_name" >&2
    failed=1
  fi
done

if docker info >/dev/null 2>&1; then
  printf 'ok: Docker daemon available\n'
else
  printf 'unavailable: Docker daemon\n' >&2
  failed=1
fi

for directory_name in "${required_directories[@]}"; do
  if [[ -d "$storage_root/$directory_name" ]]; then
    printf 'ok: storage %s\n' "$storage_root/$directory_name"
  else
    printf 'missing: storage %s\n' "$storage_root/$directory_name" >&2
    failed=1
  fi
done

exit "$failed"
