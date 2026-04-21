"""
Tests for vault.py — covers the full cache/session state machine:

  Phase 1 (cli-cache t2):
    A. Session expired  → clear cache → Phase 2
    B. Full hit         → return from cache (no BW calls)
    C. Partial hit      → fetch only missing via Phase 2
    D. All miss         → fetch all via Phase 2

  Phase 2 (BW t1):
    - ensure_bw_session() is called
    - fetched values are written to cache

  _fetch_from_bw:
    - builtin field (password, username, …)
    - custom field
    - item not found (falls back to item_name as ID)
    - bw list failure → sys.exit
"""

import json
from unittest.mock import MagicMock, call, patch

import pytest

from bw_vault.vault import _cache_key, _fetch_from_bw, resolve_fields

SESSION_KEY = b"fake-session-key"
EXPIRES_AT = 9999999999.0


def _proc(returncode=0, stdout=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    return m


# ---------------------------------------------------------------------------
# Helpers to build common patch targets
# ---------------------------------------------------------------------------

def _patch_cc_session(*, check_session=True, session_key=SESSION_KEY, expires_at=EXPIRES_AT):
    patches = [
        patch("bw_vault.vault.cc_session.check_session", return_value=check_session),
        patch("bw_vault.vault.cc_session.get_session_key", return_value=(session_key, expires_at)),
    ]
    return patches


# ---------------------------------------------------------------------------
# Phase 1-A: cli-cache session expired
# ---------------------------------------------------------------------------

class TestPhase1SessionExpired:
    def test_clears_cache_then_fetches_all(self):
        fields = {"API_KEY": "MyService:api-key"}

        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=False),
            patch("bw_vault.vault.cc_cache.clear_all_cache") as mock_clear,
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.ensure_bw_session", return_value="bw_tok"),
            patch("bw_vault.vault._fetch_from_bw", return_value="val123") as mock_fetch,
            patch("bw_vault.vault.cc_cache.write_cache"),
        ):
            result = resolve_fields(fields)

        mock_clear.assert_called_once()
        mock_fetch.assert_called_once_with("MyService", "api-key", "bw_tok")
        assert result == {"API_KEY": "val123"}

    def test_does_not_call_check_cache_when_session_expired(self):
        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=False),
            patch("bw_vault.vault.cc_cache.clear_all_cache"),
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.ensure_bw_session", return_value="tok"),
            patch("bw_vault.vault._fetch_from_bw", return_value="v"),
            patch("bw_vault.vault.cc_cache.write_cache"),
            patch("bw_vault.vault.cc_cache.check_cache") as mock_check,
        ):
            resolve_fields({"K": "I:f"})

        mock_check.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 1-B: Full cache hit
# ---------------------------------------------------------------------------

class TestPhase1FullHit:
    def test_returns_all_values_from_cache(self):
        fields = {
            "KEY_A": "ServiceA:password",
            "KEY_B": "ServiceB:api-key",
        }

        def fake_check_cache(key, session_key):
            return True

        def fake_read_cache(key, session_key):
            return "cached_" + key[-1]

        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=True),
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.cc_cache.check_cache", side_effect=fake_check_cache),
            patch("bw_vault.vault.cc_cache.read_cache", side_effect=fake_read_cache),
            patch("bw_vault.vault.ensure_bw_session") as mock_bw,
        ):
            result = resolve_fields(fields)

        mock_bw.assert_not_called()
        assert result == {
            "KEY_A": "cached_password",
            "KEY_B": "cached_api-key",
        }

    def test_does_not_write_cache_on_full_hit(self):
        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=True),
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.cc_cache.check_cache", return_value=True),
            patch("bw_vault.vault.cc_cache.read_cache", return_value="v"),
            patch("bw_vault.vault.cc_cache.write_cache") as mock_write,
        ):
            resolve_fields({"K": "I:f"})

        mock_write.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 1-C: Partial hit
# ---------------------------------------------------------------------------

class TestPhase1PartialHit:
    def test_fetches_only_missing_items(self):
        fields = {
            "HIT": "ServiceHit:password",
            "MISS": "ServiceMiss:api-key",
        }

        def fake_check(key, session_key):
            return "ServiceHit" in key

        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=True),
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.cc_cache.check_cache", side_effect=fake_check),
            patch("bw_vault.vault.cc_cache.read_cache", return_value="cached_val"),
            patch("bw_vault.vault.ensure_bw_session", return_value="bw_tok"),
            patch("bw_vault.vault._fetch_from_bw", return_value="fetched_val") as mock_fetch,
            patch("bw_vault.vault.cc_cache.write_cache"),
        ):
            result = resolve_fields(fields)

        mock_fetch.assert_called_once_with("ServiceMiss", "api-key", "bw_tok")
        assert result == {"HIT": "cached_val", "MISS": "fetched_val"}

    def test_writes_cache_for_fetched_items(self):
        fields = {"MISS": "Item:field"}

        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=True),
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.cc_cache.check_cache", return_value=False),
            patch("bw_vault.vault.ensure_bw_session", return_value="tok"),
            patch("bw_vault.vault._fetch_from_bw", return_value="fetched"),
            patch("bw_vault.vault.cc_cache.write_cache") as mock_write,
        ):
            resolve_fields(fields)

        expected_key = _cache_key("Item", "field")
        mock_write.assert_called_once_with(expected_key, "fetched", SESSION_KEY, EXPIRES_AT)


# ---------------------------------------------------------------------------
# Phase 1-D: All miss
# ---------------------------------------------------------------------------

class TestPhase1AllMiss:
    def test_fetches_all_items(self):
        fields = {"A": "Svc1:f1", "B": "Svc2:f2"}

        with (
            patch("bw_vault.vault.cc_session.check_session", return_value=True),
            patch("bw_vault.vault.cc_session.get_session_key", return_value=(SESSION_KEY, EXPIRES_AT)),
            patch("bw_vault.vault.cc_cache.check_cache", return_value=False),
            patch("bw_vault.vault.ensure_bw_session", return_value="tok"),
            patch("bw_vault.vault._fetch_from_bw", return_value="v") as mock_fetch,
            patch("bw_vault.vault.cc_cache.write_cache"),
        ):
            result = resolve_fields(fields)

        assert mock_fetch.call_count == 2
        assert result == {"A": "v", "B": "v"}


# ---------------------------------------------------------------------------
# _fetch_from_bw
# ---------------------------------------------------------------------------

class TestFetchFromBw:
    BW_SESSION = "session_tok"
    ITEMS_RESPONSE = json.dumps([{"name": "MyService", "id": "uuid-123"}])

    def test_builtin_field_uses_bw_get(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(0, self.ITEMS_RESPONSE),
                _proc(0, stdout="mypassword"),
            ]
            result = _fetch_from_bw("MyService", "password", self.BW_SESSION)

        assert result == "mypassword"
        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args == ["bw", "get", "password", "uuid-123"]

    def test_custom_field_uses_bw_get_item(self):
        item_json = json.dumps({
            "id": "uuid-123",
            "name": "MyService",
            "fields": [{"name": "api-key", "value": "secret123"}],
        })
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(0, self.ITEMS_RESPONSE),
                _proc(0, item_json),
            ]
            result = _fetch_from_bw("MyService", "api-key", self.BW_SESSION)

        assert result == "secret123"
        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args == ["bw", "get", "item", "uuid-123"]

    def test_custom_field_not_found_returns_empty(self):
        item_json = json.dumps({"id": "uuid-123", "name": "MyService", "fields": []})
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(0, self.ITEMS_RESPONSE),
                _proc(0, item_json),
            ]
            result = _fetch_from_bw("MyService", "nonexistent", self.BW_SESSION)

        assert result == ""

    def test_item_not_found_falls_back_to_name_as_id(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(0, "[]"),  # no items found
                _proc(0, stdout="fallback_val"),
            ]
            result = _fetch_from_bw("UnknownItem", "password", self.BW_SESSION)

        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args == ["bw", "get", "password", "UnknownItem"]
        assert result == "fallback_val"

    def test_exits_when_bw_list_fails(self):
        with patch("subprocess.run", return_value=_proc(1)):
            with pytest.raises(SystemExit):
                _fetch_from_bw("Item", "password", self.BW_SESSION)

    def test_bw_session_passed_in_env(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(0, self.ITEMS_RESPONSE),
                _proc(0, stdout="val"),
            ]
            _fetch_from_bw("MyService", "password", "my_session_token")

        env = mock_run.call_args_list[0][1]["env"]
        assert env["BW_SESSION"] == "my_session_token"

    @pytest.mark.parametrize("field", ["username", "password", "totp", "notes", "uri"])
    def test_all_builtin_fields_use_bw_get(self, field):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                _proc(0, self.ITEMS_RESPONSE),
                _proc(0, stdout=f"value_for_{field}"),
            ]
            result = _fetch_from_bw("MyService", field, self.BW_SESSION)

        second_call_args = mock_run.call_args_list[1][0][0]
        assert second_call_args[1] == "get"
        assert second_call_args[2] == field
        assert result == f"value_for_{field}"
