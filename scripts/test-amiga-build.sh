#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
example_directory="$repository_root/examples/hello-amiga"
artifact="$example_directory/build/hello-amiga"
profile="${AMIGALAB_FS_UAE_PROFILE:-$repository_root/fs-uae/profiles/A1200.fs-uae}"

if ! command -v m68k-amigaos-gcc >/dev/null 2>&1; then
  printf 'm68k-amigaos-gcc is unavailable. Install the GCC toolchain first.\n' >&2
  exit 1
fi

make -C "$example_directory"
if [[ ! -f "$artifact" ]]; then
  printf 'Build artifact was not created: %s\n' "$artifact" >&2
  exit 1
fi
printf 'Built Amiga executable: %s\n' "$artifact"

if [[ "${AMIGALAB_RUN_FS_UAE:-0}" == '1' ]]; then
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
