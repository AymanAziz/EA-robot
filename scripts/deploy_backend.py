#!/usr/bin/env python3
"""Plan, check or bootstrap a fresh Ubuntu backend without copying local state/secrets.

The default is an offline plan. --check only reads remote host metadata. --deploy
requires explicit SSH access and refuses a nonempty existing installation. It
does not provision a VM, configure DNS/TLS/firewalls, or authorize AI/trading.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess


INSTALL_DIR = "/opt/papertrade"
EXCLUSIONS = (
    ".git/", ".venv/", "var/", ".env", ".env.*", "**/.streamlit/secrets.toml",
    ".streamlit/secrets.toml", "__pycache__/", ".pytest_cache/", ".ruff_cache/",
    "*.egg-info/", "build/", "dist/", ".DS_Store", "*.pem", "*.key", "*.p12",
    "*.db", "*.db-*", "*.sqlite*", "*.log",
)

PROBE = r'''set -euo pipefail
python3 - <<'PY'
import json, pathlib, platform, shutil, subprocess, sys
release = {}
for line in pathlib.Path('/etc/os-release').read_text().splitlines():
    if '=' in line:
        key, value = line.split('=', 1)
        release[key] = value.strip('"')
install = pathlib.Path('/opt/papertrade')
state = 'absent'
if install.is_symlink():
    state = 'symlink'
elif install.exists():
    try:
        state = 'existing' if not install.is_dir() or any(install.iterdir()) else 'empty'
    except OSError:
        state = 'existing'
sudo = subprocess.run(['sudo', '-n', 'true'], stdout=subprocess.DEVNULL,
                      stderr=subprocess.DEVNULL).returncode == 0
print(json.dumps({'os': platform.system(), 'distribution': release.get('ID'),
                  'version': release.get('VERSION_ID'), 'architecture': platform.machine(),
                  'python': list(sys.version_info[:3]), 'rsync': bool(shutil.which('rsync')),
                  'sudo_noninteractive': sudo, 'installation': state}))
PY
'''


class DeploymentError(RuntimeError):
    pass


def ssh_target(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]{0,252}", value) or value.count("@") > 1:
        raise argparse.ArgumentTypeError("Use an SSH alias or user@hostname without shell characters")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", part) for part in value.split("@")):
        raise argparse.ArgumentTypeError("SSH username and hostname must start with a letter or number")
    return value


def api_hostname(value: str) -> str:
    value = value.rstrip(".").lower()
    try:
        ipaddress.ip_address(value)
    except ValueError:
        pass
    else:
        raise argparse.ArgumentTypeError("Use a public DNS hostname for the HTTPS backend")
    labels = value.split(".")
    if (len(labels) < 2 or len(value) > 253 or not labels[-1].isalpha()
        or value.endswith((".localhost", ".local", ".internal", ".invalid", ".test"))
        or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in labels)):
        raise argparse.ArgumentTypeError("A valid public DNS hostname is required; omit https:// and paths")
    return value


def port_number(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("SSH port must be an integer") from None
    if not 1 <= number <= 65535:
        raise argparse.ArgumentTypeError("SSH port must be between 1 and 65535")
    return number


def options(args) -> list[str]:
    values = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
              "-o", "StrictHostKeyChecking=yes", "-p", str(args.port)]
    if args.identity:
        values.extend(["-i", str(args.identity.resolve())])
    return values


def run(command, *, input=None):
    try:
        return subprocess.run(command, input=input, text=True, capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        # Never print raw SSH/package output, which may contain host-specific secrets.
        raise DeploymentError("Remote command failed; verify SSH trust, access and the server's local logs") from None


def preflight(args):
    result = run([*options(args), args.target, "bash", "-s"], input=PROBE)
    try:
        facts = json.loads(result.stdout)
        version = tuple(int(part) for part in facts["version"].split(".")[:2])
        compatible = (facts["os"] == "Linux" and facts["distribution"] == "ubuntu"
                      and version >= (24, 4) and facts["architecture"] in {"aarch64", "arm64", "x86_64"}
                      and tuple(facts["python"]) >= (3, 12) and facts["sudo_noninteractive"])
    except (ValueError, KeyError, TypeError):
        raise DeploymentError("Remote preflight returned invalid host metadata") from None
    return facts, compatible


def make_plan(args):
    return {"mode": "plan", "ssh_target": args.target, "installation": INSTALL_DIR,
            "backend_url": f"https://{args.api_hostname}" if args.api_hostname else None,
            "network_calls": False,
            "transfer": {"source": str(args.source.resolve()), "excluded": list(EXCLUSIONS),
                         "included_template": ".env.example", "delete_remote_files": False},
            "steps": ["Verify known SSH host key, Ubuntu 24.04+, Python 3.12+ and noninteractive sudo",
                      "Refuse any nonempty or symlinked existing installation",
                      "Stage source without local .env, credentials, database, models or process metadata",
                      "Generate private server-only bootstrap password/hash/token; preserve safe defaults",
                      "Run existing installer and migrations, then enable API plus engine/monitor/AI timers",
                      "Configure DNS, Caddy HTTPS and firewall separately before connecting Community Cloud"],
            "defaults": {"paper_only": True, "ai_enabled": False, "strategy_execution_enabled": False,
                         "paid_usage_authorized": False},
            "not_performed": ["VM provisioning", "DNS changes", "TLS deployment", "firewall changes",
                              "credential transfer", "model activation", "AI calls", "paper orders"]}


def deploy(args, facts):
    if facts["installation"] not in {"absent", "empty"}:
        raise DeploymentError("Existing installation detected: preserve it and follow the backed-up upgrade runbook")
    if not shutil.which("rsync"):
        raise DeploymentError("Install rsync locally before deploying")
    stage = f".cache/papertrade-upload-{secrets.token_hex(6)}"
    # The generated relative staging name contains no user-controlled shell content.
    setup = "set -euo pipefail\numask 077\n"
    if not facts["rsync"]:
        setup += "sudo -n apt-get update\nsudo -n apt-get install -y rsync\n"
    setup += f"install -d -m 0700 \"$HOME/{stage}\"\n"
    run([*options(args), args.target, "bash", "-s"], input=setup)
    transport = shlex.join(options(args))
    command = ["rsync", "--archive", "--compress", "--include=/.env.example"]
    command.extend(f"--exclude={pattern}" for pattern in EXCLUSIONS)
    command.extend(["-e", transport, str(args.source.resolve()) + "/", f"{args.target}:{stage}/"])
    run(command)
    script = f'''set -euo pipefail
PT_BACKEND_STAGE="$HOME/{stage}"
# Check again immediately before installation; a concurrent/manual setup wins.
if [[ -L {INSTALL_DIR} ]] || [[ -e {INSTALL_DIR} && ! -d {INSTALL_DIR} ]]; then
  exit 70
fi
if [[ -d {INSTALL_DIR} ]] && [[ -n "$(sudo -n ls -A {INSTALL_DIR})" ]]; then
  exit 71
fi
cd "$PT_BACKEND_STAGE"
PT_BOOTSTRAP_GENERATE=1 bash scripts/install_ubuntu.sh
sudo -n systemctl enable --now papertrade-api.service
sudo -n systemctl enable --now papertrade-engine.timer papertrade-monitor.timer papertrade-ai.timer
sudo -n -u papertrade /opt/papertrade/.venv/bin/papertrade ai-status
'''
    run([*options(args), args.target, "bash", "-s"], input=script)
    return {"mode": "deployed", "ssh_target": args.target, "paper_only": True,
            "ai_enabled": False, "strategy_execution_enabled": False,
            "bootstrap_password_file": "/opt/papertrade/var/initial-admin-password.txt",
            "backend_url": f"https://{args.api_hostname}" if args.api_hostname else None,
            "https_verified": False, "community_cloud_connected": False,
            "note": "Backend bootstrapped; DNS/TLS/firewall, provider access and strategy validation remain required"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=ssh_target)
    parser.add_argument("--api-hostname", type=api_hostname)
    parser.add_argument("--port", type=port_number, default=22)
    parser.add_argument("--identity", type=Path)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Read host metadata over SSH; do not install")
    mode.add_argument("--deploy", action="store_true", help="Bootstrap a fresh compatible host explicitly")
    args = parser.parse_args()
    try:
        if args.identity and not args.identity.is_file():
            raise DeploymentError("The selected SSH identity file does not exist")
        for name in ("pyproject.toml", "requirements.lock.txt", "scripts/install_ubuntu.sh"):
            if not (args.source / name).is_file():
                raise DeploymentError("Source must be the existing Papertrade repository root")
        if not args.check and not args.deploy:
            result = make_plan(args)
        else:
            facts, compatible = preflight(args)
            if args.check:
                result = {"mode": "check", "ssh_target": args.target, "compatible": compatible,
                          "facts": facts, "mutated": False}
            elif not compatible:
                raise DeploymentError("Host needs Ubuntu 24.04+, supported CPU, Python 3.12+ and noninteractive sudo")
            else:
                result = deploy(args, facts)
        print(json.dumps(result, indent=2))
    except DeploymentError as exc:
        print(json.dumps({"error": str(exc), "paper_only": True}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
