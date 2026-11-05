"""Fresh-backend handoff plans never touch local state or use real SSH in tests."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1] / "scripts/deploy_backend.py"
    spec = importlib.util.spec_from_file_location("papertrade_deploy_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke(helper, monkeypatch, args):
    monkeypatch.setattr("sys.argv", ["deploy_backend.py", *args])
    helper.main()


def facts(**changes):
    return {"os": "Linux", "distribution": "ubuntu", "version": "24.04", "architecture": "aarch64",
            "python": [3, 12, 3], "rsync": True, "sudo_noninteractive": True, "installation": "absent", **changes}


def test_default_plan_makes_no_network_calls_and_excludes_state(helper, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("An offline plan cannot execute SSH or rsync")
    monkeypatch.setattr(helper, "run", forbidden)
    invoke(helper, monkeypatch, ["ubuntu@vm.example.com", "--api-hostname", "api.example.com"])
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "plan" and result["network_calls"] is False
    assert {".env", "var/", ".git/", ".venv/", "**/.streamlit/secrets.toml"} <= set(result["transfer"]["excluded"])
    assert result["transfer"]["delete_remote_files"] is False
    assert not result["defaults"]["ai_enabled"] and not result["defaults"]["strategy_execution_enabled"]


@pytest.mark.parametrize("target", ["-oProxyCommand=bad", "user@host;touch bad", "user@host/path", "user@@host", "user@host\ncommand", "user@-oProxyCommand", "user@..bad"])
def test_invalid_ssh_inputs_never_execute_commands(helper, monkeypatch, target):
    monkeypatch.setattr(helper, "run", lambda *args, **kwargs: pytest.fail("Input was not rejected"))
    with pytest.raises(SystemExit) as error:
        invoke(helper, monkeypatch, [target, "--check"])
    assert error.value.code == 2


@pytest.mark.parametrize("hostname", ["http://api.example.com", "127.0.0.1", "api.local", "example.com/path", "api.example.com;command"])
def test_api_host_requires_a_public_dns_name(helper, monkeypatch, hostname):
    with pytest.raises(SystemExit) as error:
        invoke(helper, monkeypatch, ["ubuntu@vm.example.com", "--api-hostname", hostname])
    assert error.value.code == 2


def test_remote_check_is_read_only_and_keeps_host_key_verification(helper, monkeypatch, capsys):
    calls = []
    def fake(command, *, input=None):
        calls.append((command, input))
        return SimpleNamespace(stdout=json.dumps(facts()))
    monkeypatch.setattr(helper, "run", fake)
    invoke(helper, monkeypatch, ["ubuntu@vm.example.com", "--check"])
    result = json.loads(capsys.readouterr().out)
    assert result["compatible"] and result["mutated"] is False
    assert len(calls) == 1
    assert "StrictHostKeyChecking=yes" in calls[0][0]
    assert "apt-get install" not in calls[0][1]


def test_existing_remote_install_is_never_overwritten(helper, monkeypatch, capsys):
    calls = []
    def fake(command, *, input=None):
        calls.append(command)
        return SimpleNamespace(stdout=json.dumps(facts(installation="existing")))
    monkeypatch.setattr(helper, "run", fake)
    with pytest.raises(SystemExit):
        invoke(helper, monkeypatch, ["ubuntu@vm.example.com", "--deploy"])
    assert len(calls) == 1
    assert "Existing installation" in json.loads(capsys.readouterr().out)["error"]


def test_explicit_fresh_deploy_uses_generated_server_secrets_and_never_deletes_state(helper, monkeypatch, capsys):
    calls = []
    def fake(command, *, input=None):
        calls.append((command, input))
        return SimpleNamespace(stdout=json.dumps(facts()) if len(calls) == 1 else "")
    monkeypatch.setattr(helper, "run", fake)
    monkeypatch.setattr(helper.shutil, "which", lambda _: "/usr/bin/rsync")
    invoke(helper, monkeypatch, ["ubuntu@vm.example.com", "--deploy", "--api-hostname", "api.example.com"])
    result = json.loads(capsys.readouterr().out)
    assert result["mode"] == "deployed" and not result["https_verified"]
    transfer = next(command for command, _ in calls if command[0] == "rsync")
    assert "--delete" not in transfer and "--exclude=var/" in transfer and "--include=/.env.example" in transfer
    bootstrap = calls[-1][1]
    assert "PT_BOOTSTRAP_GENERATE=1" in bootstrap
    assert "papertrade-ai.timer" in bootstrap and "papertrade-monitor.timer" in bootstrap
    assert "PT_AI_ENABLED=true" not in bootstrap and "PT_STRATEGY_EXECUTION_ENABLED=true" not in bootstrap
    assert "caddy" not in bootstrap and "ufw" not in bootstrap
