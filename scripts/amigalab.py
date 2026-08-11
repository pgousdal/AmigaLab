#!/usr/bin/env python3
"""AmigaLab M3 profile preflight and deliberate manual launcher."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from emulation.profiles import PreflightResult, preflight, render_fs_uae


REPOSITORY = Path(__file__).resolve().parents[1]


def _profile_path(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_file():
        return candidate
    return REPOSITORY / "profiles" / f"{value}.json"


def _print_report(result: PreflightResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return
    print(f"Profile: {result.profile_id} — {result.profile_name}")
    print(f"Schema: {result.schema_version}; machine: {result.machine}")
    for asset in result.assets:
        print(f"Asset {asset.id}: {asset.path or '(unresolved)'}; exists={asset.exists}; hash={asset.hash_status}")
    for mount in result.mounts:
        mode = "writable" if mount["writable"] else "read-only"
        print(f"Mount {mount['device']}: {mount['trust_zone']}; {mode}; {mount['path']}")
    print(f"Generated config: {result.config_path}")
    print(f"Runtime state: {result.runtime_path}")
    for issue in result.issues:
        print(f"ERROR [{issue.code}] {issue.path}: {issue.message}", file=sys.stderr)
    print("Launchable: yes" if result.launchable else "Launchable: no")


def _run_preflight(args: argparse.Namespace):
    return preflight(_profile_path(args.profile), Path(args.inventory), Path(args.runtime_root))


def command_preflight(args: argparse.Namespace) -> int:
    _, _, result = _run_preflight(args)
    _print_report(result, args.json)
    return 0 if result.launchable else 2


def command_launch(args: argparse.Namespace) -> int:
    profile, assets, result = _run_preflight(args)
    _print_report(result, args.json)
    if not result.launchable or profile is None:
        return 2
    executable = args.fs_uae if args.dry_run else shutil.which(args.fs_uae)
    if executable is None:
        print(f"ERROR: FS-UAE executable not found: {args.fs_uae}", file=sys.stderr)
        return 3
    config_path = Path(result.config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    Path(result.runtime_path).mkdir(parents=True, exist_ok=True)
    config_path.write_text(render_fs_uae(profile, assets, Path(result.runtime_path)), encoding="utf-8")
    command = [executable, str(config_path)]
    print("Command: " + json.dumps(command))
    if args.dry_run:
        return 0
    return subprocess.run(command, check=False).returncode


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    for name, function in (("profile-preflight", command_preflight), ("profile-launch", command_launch)):
        command = subcommands.add_parser(name)
        command.add_argument("profile", help="profile ID or JSON path")
        command.add_argument("--inventory", default=str(REPOSITORY / "config" / "assets.local.json"))
        command.add_argument("--runtime-root", default=str(REPOSITORY / "runtime" / "profiles"))
        command.add_argument("--json", action="store_true")
        if name == "profile-launch":
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--fs-uae", default="fs-uae")
        command.set_defaults(function=function)
    return result


def main() -> int:
    args = parser().parse_args()
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
