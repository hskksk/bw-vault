import os
import sys
from unittest.mock import patch

import pytest

from bw_vault.main import cmd_exec, cmd_run, main


class TestMain:
    def test_no_args_exits(self):
        with patch.object(sys, "argv", ["bw-vault"]):
            with pytest.raises(SystemExit):
                main()

    def test_unknown_command_exits(self):
        with patch.object(sys, "argv", ["bw-vault", "unknown"]):
            with pytest.raises(SystemExit):
                main()

    def test_dispatches_exec(self):
        with (
            patch.object(sys, "argv", ["bw-vault", "exec", "--", "env"]),
            patch("bw_vault.main.cmd_exec") as mock_exec,
        ):
            main()
        mock_exec.assert_called_once_with(["--", "env"])

    def test_dispatches_run(self):
        with (
            patch.object(sys, "argv", ["bw-vault", "run", "env"]),
            patch("bw_vault.main.cmd_run") as mock_run,
        ):
            main()
        mock_run.assert_called_once_with(["env"])


class TestCmdExec:
    def _run(self, args, config=None, resolved=None, session="tok123"):
        config = config or {"default": {}}
        resolved = resolved or {}
        with (
            patch("bw_vault.main.load_config", return_value=config),
            patch("bw_vault.main.get_profile", return_value=config.get("default", {})),
            patch("bw_vault.main.ensure_bw_session", return_value=session),
            patch("bw_vault.main.resolve_fields", return_value=resolved),
            patch("os.execvpe") as mock_exec,
        ):
            cmd_exec(args)
        return mock_exec

    def test_uses_default_profile_when_no_args(self):
        with (
            patch("bw_vault.main.load_config", return_value={}),
            patch("bw_vault.main.get_profile", return_value={}) as mock_get,
            patch("bw_vault.main.ensure_bw_session", return_value="tok"),
            patch("bw_vault.main.resolve_fields", return_value={}),
            patch("os.execvpe"),
        ):
            cmd_exec([])
        mock_get.assert_called_once_with({}, "default")

    def test_uses_named_profile(self):
        config = {"work": {"K": "I:f"}}
        with (
            patch("bw_vault.main.load_config", return_value=config),
            patch("bw_vault.main.get_profile", return_value={"K": "I:f"}) as mock_get,
            patch("bw_vault.main.ensure_bw_session", return_value="tok"),
            patch("bw_vault.main.resolve_fields", return_value={}),
            patch("os.execvpe"),
        ):
            cmd_exec(["work"])
        mock_get.assert_called_once_with(config, "work")

    def test_executes_specified_command(self):
        mock_exec = self._run(["--", "echo", "hello"], resolved={"K": "v"})
        mock_exec.assert_called_once()
        args = mock_exec.call_args[0]
        assert args[0] == "echo"
        assert args[1] == ["echo", "hello"]

    def test_executes_shell_when_no_command(self, monkeypatch):
        monkeypatch.setenv("SHELL", "/bin/zsh")
        mock_exec = self._run([])
        args = mock_exec.call_args[0]
        assert args[0] == "/bin/zsh"

    def test_injects_bw_session(self):
        mock_exec = self._run(["--", "env"], session="mysession")
        env = mock_exec.call_args[0][2]
        assert env["BW_SESSION"] == "mysession"

    def test_injects_resolved_env_vars(self):
        resolved = {"MY_KEY": "secret_value"}
        mock_exec = self._run(["--", "env"], resolved=resolved)
        env = mock_exec.call_args[0][2]
        assert env["MY_KEY"] == "secret_value"

    def test_profile_before_double_dash(self):
        config = {"staging": {}}
        with (
            patch("bw_vault.main.load_config", return_value=config),
            patch("bw_vault.main.get_profile", return_value={}) as mock_get,
            patch("bw_vault.main.ensure_bw_session", return_value="tok"),
            patch("bw_vault.main.resolve_fields", return_value={}),
            patch("os.execvpe"),
        ):
            cmd_exec(["staging", "--", "printenv"])
        mock_get.assert_called_once_with(config, "staging")


class TestCmdRun:
    def test_no_args_exits(self):
        with pytest.raises(SystemExit):
            cmd_run([])

    def test_executes_command_with_bw_session(self):
        with (
            patch("bw_vault.main.ensure_bw_session", return_value="tok123"),
            patch("os.execvpe") as mock_exec,
        ):
            cmd_run(["printenv", "BW_SESSION"])

        mock_exec.assert_called_once()
        cmd_arg, argv_arg, env_arg = mock_exec.call_args[0]
        assert cmd_arg == "printenv"
        assert argv_arg == ["printenv", "BW_SESSION"]
        assert env_arg["BW_SESSION"] == "tok123"

    def test_forwards_all_args(self):
        with (
            patch("bw_vault.main.ensure_bw_session", return_value="tok"),
            patch("os.execvpe") as mock_exec,
        ):
            cmd_run(["some-cmd", "--flag", "value"])

        _, argv_arg, _ = mock_exec.call_args[0]
        assert argv_arg == ["some-cmd", "--flag", "value"]
