#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
storage_root="${AMIGALAB_STORAGE_ROOT:-/srv/amigalab}"
example_directory="$repository_root/examples/hello-amiga"
artifact="$example_directory/build/hello-amiga"

for required_directory in "$storage_root/shared" "$example_directory"; do
  if [[ ! -d "$required_directory" ]]; then
    printf 'Required directory is missing: %s\nRun the AmigaLab Ansible playbook first.\n' "$required_directory" >&2
    exit 1
  fi
done
if ! command -v m68k-amigaos-gcc >/dev/null 2>&1; then
  printf 'm68k-amigaos-gcc is unavailable. Install the GCC toolchain and open a new shell.\n' >&2
  exit 1
fi

if ! make -C "$example_directory"; then
  printf 'The hello-amiga build failed. Check the compiler and its C runtime configuration.\n' >&2
  exit 1
fi
if [[ ! -f "$artifact" ]]; then
  printf 'Expected build artifact is missing: %s\n' "$artifact" >&2
  exit 1
fi
printf 'Amiga build succeeded: %s\n' "$artifact"
