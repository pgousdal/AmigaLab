#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$repository_root/scripts/test-amiga.sh"

if [[ "${AMIGALAB_RUN_FS_UAE:-0}" == '1' ]]; then
  profile="${AMIGALAB_FS_UAE_PROFILE:-$repository_root/fs-uae/profiles/A1200.fs-uae}"
  if ! command -v fs-uae >/dev/null 2>&1; then
    printf 'FS-UAE is unavailable.\n' >&2
    exit 1
  fi
  if [[ ! -f "$profile" ]]; then
    printf 'FS-UAE profile does not exist: %s\n' "$profile" >&2
    exit 1
  fi
  printf 'Launching FS-UAE with %s\n' "$profile"
  exec fs-uae "$profile"
fi
