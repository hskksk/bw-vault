import textwrap
from pathlib import Path

import pytest

from bw_vault.config import get_profile, load_config


def test_load_config_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert load_config() == {}


def test_load_config_parses_toml(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg_dir = tmp_path / "bw-vault"
    cfg_dir.mkdir()
    (cfg_dir / "config.toml").write_text(
        textwrap.dedent("""\
            [default]
            API_KEY = "MyService:api-key"

            [work]
            DB_PASS = "DB:password"
        """)
    )
    config = load_config()
    assert config == {
        "default": {"API_KEY": "MyService:api-key"},
        "work": {"DB_PASS": "DB:password"},
    }


def test_get_profile_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    (tmp_path / "bw-vault").mkdir()
    (tmp_path / "bw-vault" / "config.toml").write_text("[default]\nK = \"Item:field\"\n")
    config = load_config()
    assert get_profile(config, "default") == {"K": "Item:field"}


def test_get_profile_missing_returns_empty():
    assert get_profile({}, "nonexistent") == {}


def test_get_profile_does_not_affect_other_profiles():
    config = {
        "a": {"X": "Foo:bar"},
        "b": {"Y": "Baz:qux"},
    }
    assert get_profile(config, "a") == {"X": "Foo:bar"}
    assert get_profile(config, "b") == {"Y": "Baz:qux"}
