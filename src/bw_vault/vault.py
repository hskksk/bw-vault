import json
import os
import subprocess
import sys

from cli_cache import cache as cc_cache
from cli_cache import session as cc_session

from .bw_session import ensure_bw_session

_CACHE_PREFIX = ["bw-vault", "field"]
_SESSION_TTL = 86400  # 24h; matches cli-cache default


def _cache_key(item_name: str, field_name: str) -> list[str]:
    return _CACHE_PREFIX + [item_name, field_name]


def _fetch_from_bw(item_name: str, field_name: str, bw_session: str) -> str:
    env = {**os.environ, "BW_SESSION": bw_session}

    # Resolve item name → ID
    list_result = subprocess.run(
        ["bw", "list", "items", "--search", item_name],
        env=env,
        capture_output=True,
        text=True,
    )
    if list_result.returncode != 0:
        print(f"bw list items failed for '{item_name}'", file=sys.stderr)
        sys.exit(1)

    items = json.loads(list_result.stdout or "[]")
    matched = [i for i in items if i.get("name") == item_name]
    item_id = matched[0]["id"] if matched else item_name

    builtin_fields = {"username", "password", "totp", "notes", "uri"}
    if field_name in builtin_fields:
        result = subprocess.run(
            ["bw", "get", field_name, item_id],
            env=env,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    result = subprocess.run(
        ["bw", "get", "item", item_id],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    item_data = json.loads(result.stdout)
    for field in item_data.get("fields", []):
        if field.get("name") == field_name:
            return field.get("value", "")
    return ""


def resolve_fields(fields: dict[str, str]) -> dict[str, str]:
    """
    Resolve {ENV_VAR: "item_name:field_name"} using the cache/session state machine.

    Phase 1 – Cache session check (cli-cache t2):
      - Session expired → clear all cache → Phase 2
      - Session active → check each item:
          Full hit  → return from cache
          Any miss  → Phase 2

    Phase 2 – Bitwarden session check (BW t1):
      - Unlock vault if needed → fetch missing items → update cache
    """
    parsed: list[tuple[str, str, str]] = []
    for env_var, spec in fields.items():
        item_name, _, field_name = spec.partition(":")
        parsed.append((env_var, item_name, field_name))

    # Phase 1: Cache session check
    if not cc_session.check_session():
        cc_cache.clear_all_cache()
        return _phase2(parsed, need_all=True)

    session_key, expires_at = cc_session.get_session_key(_SESSION_TTL)

    result: dict[str, str] = {}
    missing: list[tuple[str, str, str]] = []

    for env_var, item_name, field_name in parsed:
        key = _cache_key(item_name, field_name)
        if cc_cache.check_cache(key, session_key):
            value = cc_cache.read_cache(key, session_key)
            result[env_var] = value or ""
        else:
            missing.append((env_var, item_name, field_name))

    if not missing:
        return result  # Full hit

    # Phase 2: fetch missing items
    fetched = _phase2(missing, need_all=False)
    result.update(fetched)
    return result


def _phase2(
    items: list[tuple[str, str, str]], *, need_all: bool
) -> dict[str, str]:
    """Ensure BW session and fetch items, updating cache."""
    bw_session = ensure_bw_session()
    session_key, expires_at = cc_session.get_session_key(_SESSION_TTL)

    result: dict[str, str] = {}
    for env_var, item_name, field_name in items:
        value = _fetch_from_bw(item_name, field_name, bw_session)
        key = _cache_key(item_name, field_name)
        cc_cache.write_cache(key, value, session_key, expires_at)
        result[env_var] = value
    return result
