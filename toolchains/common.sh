#!/usr/bin/env bash
# Shared helpers for AmigaLab toolchain installers. Source this file; do not run it.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  printf 'common.sh must be sourced by an AmigaLab toolchain installer.\n' >&2
  exit 1
fi

AMIGALAB_ROOT="${AMIGALAB_ROOT:-/opt/amigalab}"
AMIGALAB_TOOLCHAIN="${AMIGALAB_TOOLCHAIN:-$AMIGALAB_ROOT/toolchains}"
TOOLCHAIN_PREFIX="${TOOLCHAIN_PREFIX:-$AMIGALAB_TOOLCHAIN}"
export AMIGALAB_ROOT AMIGALAB_TOOLCHAIN TOOLCHAIN_PREFIX

require_commands() {
  local command_name
  local missing=()
  for command_name in "$@"; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
      missing+=("$command_name")
    fi
  done
  if (( ${#missing[@]} > 0 )); then
    printf 'Missing required command(s): %s\n' "${missing[*]}" >&2
    exit 1
  fi
}

create_toolchain_directories() {
  install -d "$TOOLCHAIN_PREFIX/bin" "$TOOLCHAIN_PREFIX/src"
}

verify_optional_sha256() {
  local archive_path="$1"
  local expected_sha256="$2"
  if [[ -n "$expected_sha256" ]]; then
    printf '%s  %s\n' "$expected_sha256" "$archive_path" | sha256sum --check --status
  fi
}
