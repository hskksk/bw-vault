import os
import tomllib
from pathlib import Path


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(base) / "bw-vault" / "config.toml"


def load_config() -> dict[str, dict[str, str]]:
    path = config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


def get_profile(config: dict[str, dict[str, str]], profile: str) -> dict[str, str]:
    """Return {ENV_VAR: "item_name:field_name"} for the given profile."""
    return config.get(profile, {})
