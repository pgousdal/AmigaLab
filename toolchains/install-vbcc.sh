#!/usr/bin/env bash
set -euo pipefail

toolchain_prefix="${TOOLCHAIN_PREFIX:-/opt/amigalab/toolchains}"
vbcc_archive="${VBCC_ARCHIVE:?Set VBCC_ARCHIVE to a lawfully obtained VBCC archive.}"
expected_sha256="${VBCC_SHA256:-}"

if [[ ! -f "$vbcc_archive" ]]; then
  printf 'VBCC archive not found: %s\n' "$vbcc_archive" >&2
  exit 1
fi
if [[ -n "$expected_sha256" ]]; then
  printf '%s  %s\n' "$expected_sha256" "$vbcc_archive" | sha256sum --check --status
fi

work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT
mkdir -p "$toolchain_prefix/vbcc" "$toolchain_prefix/bin"
tar --extract --file "$vbcc_archive" --directory "$work_directory"
archive_root="$(find "$work_directory" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$archive_root" ]]; then
  printf 'VBCC archive does not contain a top-level directory.\n' >&2
  exit 1
fi
rm -rf "$toolchain_prefix/vbcc"
mv "$archive_root" "$toolchain_prefix/vbcc"
compiler_path="$(find "$toolchain_prefix/vbcc" -type f -name vc -perm -u+x | head -n 1)"
if [[ -z "$compiler_path" ]]; then
  printf 'Could not find executable vc in the VBCC archive.\n' >&2
  exit 1
fi
ln -sfn "$compiler_path" "$toolchain_prefix/bin/vc"
printf 'Installed VBCC in %s/vbcc\n' "$toolchain_prefix"
