#!/usr/bin/env bash
set -euo pipefail

toolchain_prefix="${TOOLCHAIN_PREFIX:-/opt/amigalab/toolchains}"
source_url="${VLINK_SOURCE_URL:-https://sun.hasenbraten.de/vlink/release/vlink.tar.gz}"
expected_sha256="${VLINK_SHA256:-}"
work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT

curl --fail --location --silent --show-error "$source_url" --output "$work_directory/vlink.tar.gz"
if [[ -n "$expected_sha256" ]]; then
  printf '%s  %s\n' "$expected_sha256" "$work_directory/vlink.tar.gz" | sha256sum --check --status
fi
mkdir -p "$work_directory/source" "$toolchain_prefix/bin"
tar --extract --file "$work_directory/vlink.tar.gz" --strip-components=1 --directory "$work_directory/source"
make -C "$work_directory/source"
install -m 0755 "$work_directory/source/vlink" "$toolchain_prefix/bin/vlink"
printf 'Installed vlink in %s/bin\n' "$toolchain_prefix"
