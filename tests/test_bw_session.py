import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from bw_vault.bw_session import (
    _bw_unlock,
    _check_bw_session,
    _decrypt_age_password,
    ensure_bw_session,
)


def _proc(returncode: int = 0, stdout: str = "") -> MagicMock:
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


class TestCheckBwSession:
    def test_returns_true_when_bw_succeeds(self):
        with patch("subprocess.run", return_value=_proc(0)) as mock_run:
            assert _check_bw_session("token123") is True
        args = mock_run.call_args[0][0]
        assert args == ["bw", "unlock", "--check"]

    def test_passes_token_in_env(self):
        with patch("subprocess.run", return_value=_proc(0)) as mock_run:
            _check_bw_session("mytoken")
        env = mock_run.call_args[1]["env"]
        assert env["BW_SESSION"] == "mytoken"

    def test_returns_false_when_bw_fails(self):
        with patch("subprocess.run", return_value=_proc(1)):
            assert _check_bw_session("bad") is False


class TestDecryptAgePassword:
    def test_returns_password_on_success(self):
        with patch("subprocess.run", return_value=_proc(0, stdout="secret\n")):
            assert _decrypt_age_password() == "secret"

    def test_exits_on_failure(self):
        with patch("subprocess.run", return_value=_proc(1)):
            with pytest.raises(SystemExit):
                _decrypt_age_password()


class TestBwUnlock:
    def test_returns_token_on_success(self):
        with patch("subprocess.run", return_value=_proc(0, stdout="SESSION_TOKEN\n")):
            assert _bw_unlock("password") == "SESSION_TOKEN"

    def test_passes_password_in_env(self):
        with patch("subprocess.run", return_value=_proc(0, stdout="tok")) as mock_run:
            _bw_unlock("mypassword")
        env = mock_run.call_args[1]["env"]
        assert env["BW_PASSWORD"] == "mypassword"

    def test_exits_on_failure(self):
        with patch("subprocess.run", return_value=_proc(1)):
            with pytest.raises(SystemExit):
                _bw_unlock("password")


class TestEnsureBwSession:
    def test_returns_stored_token_when_valid(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        session_file = tmp_path / "bw-vault" / "session"
        session_file.parent.mkdir(parents=True)
        session_file.write_text("stored_token")

        with patch("bw_vault.bw_session._check_bw_session", return_value=True):
            token = ensure_bw_session()

        assert token == "stored_token"

    def test_returns_env_token_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.setenv("BW_SESSION", "env_token")

        with patch("bw_vault.bw_session._check_bw_session", return_value=True):
            token = ensure_bw_session()

        assert token == "env_token"

    def test_unlocks_when_stored_token_invalid(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        session_file = tmp_path / "bw-vault" / "session"
        session_file.parent.mkdir(parents=True)
        session_file.write_text("stale_token")

        with (
            patch("bw_vault.bw_session._check_bw_session", return_value=False),
            patch("bw_vault.bw_session._decrypt_age_password", return_value="pass"),
            patch("bw_vault.bw_session._bw_unlock", return_value="new_token") as mock_unlock,
        ):
            token = ensure_bw_session()

        assert token == "new_token"
        mock_unlock.assert_called_once_with("pass")

    def test_unlocks_when_no_token_available(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.delenv("BW_SESSION", raising=False)

        with (
            patch("bw_vault.bw_session._decrypt_age_password", return_value="pass"),
            patch("bw_vault.bw_session._bw_unlock", return_value="fresh_token"),
        ):
            token = ensure_bw_session()

        assert token == "fresh_token"

    def test_writes_new_token_to_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        monkeypatch.delenv("BW_SESSION", raising=False)

        with (
            patch("bw_vault.bw_session._decrypt_age_password", return_value="pass"),
            patch("bw_vault.bw_session._bw_unlock", return_value="written_token"),
        ):
            ensure_bw_session()

        session_file = tmp_path / "bw-vault" / "session"
        assert session_file.read_text() == "written_token"
        assert oct(session_file.stat().st_mode)[-3:] == "600"
