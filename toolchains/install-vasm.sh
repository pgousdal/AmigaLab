#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$script_directory/common.sh"
source_url="${VASM_SOURCE_URL:-https://sun.hasenbraten.de/vasm/release/vasm.tar.gz}"
expected_sha256="${VASM_SHA256:-}"
work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT

require_commands curl install make mktemp sha256sum tar
curl --fail --location --silent --show-error "$source_url" --output "$work_directory/vasm.tar.gz"
verify_optional_sha256 "$work_directory/vasm.tar.gz" "$expected_sha256"
mkdir -p "$work_directory/source"
create_toolchain_directories
tar --extract --file "$work_directory/vasm.tar.gz" --strip-components=1 --directory "$work_directory/source"
make -C "$work_directory/source" CPU=m68k SYNTAX=mot
install -m 0755 "$work_directory/source/vasmm68k_mot" "$TOOLCHAIN_PREFIX/bin/vasmm68k_mot"
printf 'Installed vasmm68k_mot in %s/bin\n' "$TOOLCHAIN_PREFIX"
