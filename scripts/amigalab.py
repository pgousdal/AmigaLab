#!/usr/bin/env python3
"""AmigaLab M3 profile preflight and deliberate manual launcher."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from emulation.profiles import PreflightResult, preflight, render_fs_uae
from emulation.sessions import SessionConflict, SessionStore, launch_session, plan_session, session_status
from emulation.appliance import ApplianceConfig, appliance_check, load_appliance_config, save_appliance_config


REPOSITORY = Path(__file__).resolve().parents[1]


def _appliance_config(args: argparse.Namespace):
    return load_appliance_config(Path(args.config), missing_ok=True)


def command_appliance_status(args: argparse.Namespace) -> int:
    try:
        config = _appliance_config(args)
        if getattr(args, "profile", None):
            config = ApplianceConfig(1, config.enabled, args.profile)
        report = appliance_check(config, REPOSITORY, Path(args.inventory), Path(args.runtime_root), args.fs_uae)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: invalid appliance configuration: {error}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True) if args.json else
          f"Appliance: {'enabled' if config.enabled else 'disabled'}\nProfile: {config.profile_id or 'none'}\nReady: {'yes' if report['ready'] else 'no'}\nService: {report['service']}\nRecovery: Ctrl-Alt-F2 or independently configured SSH")
    return 0 if report["ready"] or (args.command == "appliance-status" and not config.enabled) else 2


def command_appliance_enable(args: argparse.Namespace) -> int:
    config = ApplianceConfig(1, True, args.profile)
    report = appliance_check(config, REPOSITORY, Path(args.inventory), Path(args.runtime_root), args.fs_uae)
    if not report["ready"]:
        print(json.dumps(report, indent=2, sort_keys=True), file=sys.stderr)
        return 2
    save_appliance_config(Path(args.config), config)
    print(f"Appliance intent enabled for {args.profile}; run the Ansible playbook to reconcile the host.")
    return 0


def command_appliance_disable(args: argparse.Namespace) -> int:
    prior = _appliance_config(args)
    save_appliance_config(Path(args.config), ApplianceConfig(1, False, prior.profile_id))
    print("Appliance intent disabled; run the Ansible playbook to remove automatic login.")
    return 0


def command_appliance_run(args: argparse.Namespace) -> int:
    try:
        config = load_appliance_config(Path(args.config))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: invalid appliance configuration: {error}", file=sys.stderr); return 2
    if not config.enabled:
        print("ERROR: appliance mode is disabled", file=sys.stderr); return 2
    args.profile = config.profile_id
    args.dry_run = False
    args.json = False
    args.command = "session-launch"
    return command_launch(args)


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
    executable = args.fs_uae if args.dry_run else shutil.which(args.fs_uae)
    plan = plan_session(_profile_path(args.profile), Path(args.inventory), Path(args.runtime_root), executable or args.fs_uae)
    _print_report(plan.preflight, args.json)
    if not plan.preflight.launchable or plan.profile is None:
        return 2
    if executable is None:
        print(f"ERROR: FS-UAE executable not found: {args.fs_uae}", file=sys.stderr)
        return 3
    print(f"Session: {plan.session_id}")
    print(f"Session directory: {plan.session_dir}")
    print("Command: " + json.dumps(list(plan.argv)))
    if args.dry_run:
        # Preserve M3.0.1's legacy deterministic render contract.  The new
        # session-launch dry run remains entirely side-effect free.
        if args.command == "profile-launch":
            profile, assets, legacy = _run_preflight(args)
            config_path = Path(legacy.config_path)
            config_path.parent.mkdir(parents=True, exist_ok=True)
            Path(legacy.runtime_path).mkdir(parents=True, exist_ok=True)
            config_path.write_text(render_fs_uae(profile, assets, Path(legacy.runtime_path)), encoding="utf-8")
        return 0
    try:
        state = launch_session(plan, Path(args.runtime_root))
    except SessionConflict as error:
        print(f"ERROR: {error}; inspect with session-status", file=sys.stderr)
        return 4
    except OSError as error:
        print(f"ERROR: session launch failed: {error}", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
    return 0 if state.state in {"exited", "interrupted"} else (state.exit_code or 1)


def command_session_status(args: argparse.Namespace) -> int:
    value = session_status(Path(args.runtime_root))
    if args.json:
        print(json.dumps(value, indent=2, sort_keys=True))
    else:
        print(f"Lock: {value['lock']['status']}")
        print(f"Active session: {value['active_session'] or 'none'}")
        print(f"Stale/incomplete: {'yes' if value['stale_or_incomplete'] else 'no'}")
        recent = value["most_recent_session"]
        print(f"Most recent: {recent['session_id']} ({recent['state']})" if recent else "Most recent: none")
    return 0


def command_session_show(args: argparse.Namespace) -> int:
    try:
        state = SessionStore(Path(args.runtime_root)).load(args.session_id)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
        print(f"ERROR: cannot load session: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(state.to_dict(), indent=2, sort_keys=True))
    else:
        for key, value in state.to_dict().items():
            print(f"{key}: {value}")
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subcommands = result.add_subparsers(dest="command", required=True)
    for name, function in (("profile-preflight", command_preflight), ("profile-launch", command_launch), ("session-launch", command_launch)):
        command = subcommands.add_parser(name)
        command.add_argument("profile", help="profile ID or JSON path")
        command.add_argument("--inventory", default=str(REPOSITORY / "config" / "assets.local.json"))
        command.add_argument("--runtime-root", default=str(REPOSITORY / "runtime" / "profiles"))
        command.add_argument("--json", action="store_true")
        if name in {"profile-launch", "session-launch"}:
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--fs-uae", default="fs-uae")
        command.set_defaults(function=function)
    for name, function in (("session-status", command_session_status), ("session-show", command_session_show)):
        command = subcommands.add_parser(name)
        if name == "session-show":
            command.add_argument("session_id")
        command.add_argument("--runtime-root", default=str(REPOSITORY / "runtime" / "profiles"))
        command.add_argument("--json", action="store_true")
        command.set_defaults(function=function)
    appliance_default = str(REPOSITORY / "config" / "appliance.local.json")
    for name, function in (("appliance-status", command_appliance_status), ("appliance-check", command_appliance_status),
                           ("appliance-enable", command_appliance_enable), ("appliance-disable", command_appliance_disable),
                           ("appliance-run", command_appliance_run)):
        command = subcommands.add_parser(name)
        if name == "appliance-enable": command.add_argument("profile")
        if name == "appliance-check": command.add_argument("profile", nargs="?")
        command.add_argument("--config", default=appliance_default)
        command.add_argument("--inventory", default=str(REPOSITORY / "config" / "assets.local.json"))
        command.add_argument("--runtime-root", default=str(REPOSITORY / "runtime" / "profiles"))
        command.add_argument("--fs-uae", default="fs-uae")
        command.add_argument("--json", action="store_true")
        command.set_defaults(function=function)
    return result


def main() -> int:
    args = parser().parse_args()
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
