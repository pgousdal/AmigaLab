#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$script_directory/common.sh"
vbcc_archive="${VBCC_ARCHIVE:?Set VBCC_ARCHIVE to a lawfully obtained VBCC archive.}"
expected_sha256="${VBCC_SHA256:-}"

require_commands find head install ln mktemp rm sha256sum tar
if [[ ! -f "$vbcc_archive" ]]; then
  printf 'VBCC archive not found: %s\n' "$vbcc_archive" >&2
  exit 1
fi
verify_optional_sha256 "$vbcc_archive" "$expected_sha256"

work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT
create_toolchain_directories
tar --extract --file "$vbcc_archive" --directory "$work_directory"
archive_root="$(find "$work_directory" -mindepth 1 -maxdepth 1 -type d | head -n 1)"
if [[ -z "$archive_root" ]]; then
  printf 'VBCC archive does not contain a top-level directory.\n' >&2
  exit 1
fi
rm -rf "$TOOLCHAIN_PREFIX/vbcc"
mv "$archive_root" "$TOOLCHAIN_PREFIX/vbcc"
compiler_path="$(find "$TOOLCHAIN_PREFIX/vbcc" -type f -name vc -perm -u+x | head -n 1)"
if [[ -z "$compiler_path" ]]; then
  printf 'Could not find executable vc in the VBCC archive.\n' >&2
  exit 1
fi
ln -sfn "$compiler_path" "$TOOLCHAIN_PREFIX/bin/vc"
printf 'Installed VBCC in %s/vbcc\n' "$TOOLCHAIN_PREFIX"
