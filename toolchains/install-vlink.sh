#!/usr/bin/env bash
set -euo pipefail

script_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
source "$script_directory/common.sh"
source_url="${VLINK_SOURCE_URL:-https://sun.hasenbraten.de/vlink/release/vlink.tar.gz}"
expected_sha256="${VLINK_SHA256:-}"
work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT

require_commands curl install make mktemp sha256sum tar
curl --fail --location --silent --show-error "$source_url" --output "$work_directory/vlink.tar.gz"
verify_optional_sha256 "$work_directory/vlink.tar.gz" "$expected_sha256"
mkdir -p "$work_directory/source"
create_toolchain_directories
tar --extract --file "$work_directory/vlink.tar.gz" --strip-components=1 --directory "$work_directory/source"
make -C "$work_directory/source"
install -m 0755 "$work_directory/source/vlink" "$TOOLCHAIN_PREFIX/bin/vlink"
printf 'Installed vlink in %s/bin\n' "$TOOLCHAIN_PREFIX"
