#!/usr/bin/env bash
set -euo pipefail

toolchain_prefix="${TOOLCHAIN_PREFIX:-/opt/amigalab/toolchains}"
source_url="${VASM_SOURCE_URL:-https://sun.hasenbraten.de/vasm/release/vasm.tar.gz}"
expected_sha256="${VASM_SHA256:-}"
work_directory="$(mktemp -d)"
trap 'rm -rf "$work_directory"' EXIT

curl --fail --location --silent --show-error "$source_url" --output "$work_directory/vasm.tar.gz"
if [[ -n "$expected_sha256" ]]; then
  printf '%s  %s\n' "$expected_sha256" "$work_directory/vasm.tar.gz" | sha256sum --check --status
fi
mkdir -p "$work_directory/source" "$toolchain_prefix/bin"
tar --extract --file "$work_directory/vasm.tar.gz" --strip-components=1 --directory "$work_directory/source"
make -C "$work_directory/source" CPU=m68k SYNTAX=mot
install -m 0755 "$work_directory/source/vasmm68k_mot" "$toolchain_prefix/bin/vasmm68k_mot"
printf 'Installed vasmm68k_mot in %s/bin\n' "$toolchain_prefix"
