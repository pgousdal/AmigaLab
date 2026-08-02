#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -r /etc/os-release ]]; then
  printf 'Cannot identify the operating system: /etc/os-release is missing.\n' >&2
  exit 1
fi

. /etc/os-release
if [[ "${ID:-}" != "debian" ]]; then
  printf 'AmigaLab bootstrap supports Debian only (detected: %s).\n' "${ID:-unknown}" >&2
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  printf 'sudo is required to install packages and run the playbook.\n' >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install --yes ansible
sudo env ANSIBLE_CONFIG="$repository_root/ansible.cfg" ansible-playbook -i "$repository_root/ansible/inventory/hosts.ini" \
  "$repository_root/ansible/playbooks/site.yml"
