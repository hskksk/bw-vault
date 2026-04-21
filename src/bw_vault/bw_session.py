import os
import subprocess
import sys
from pathlib import Path


def _session_file() -> Path:
    base = os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")
    return Path(base) / "bw-vault" / "session"


def _check_bw_session(token: str) -> bool:
    result = subprocess.run(
        ["bw", "unlock", "--check"],
        env={**os.environ, "BW_SESSION": token},
        capture_output=True,
    )
    return result.returncode == 0


def _decrypt_age_password() -> str:
    age_file = Path.home() / ".bw_pass.age"
    result = subprocess.run(["age", "-d", str(age_file)], capture_output=True, text=True)
    if result.returncode != 0:
        print("Failed to decrypt password.", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def _bw_unlock(password: str) -> str:
    result = subprocess.run(
        ["bw", "unlock", "--passwordenv", "BW_PASSWORD", "--raw"],
        env={**os.environ, "BW_PASSWORD": password},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("Failed to unlock Bitwarden vault.", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def ensure_bw_session() -> str:
    """Return a valid BW_SESSION token, unlocking the vault if necessary."""
    session_file = _session_file()

    token = None
    if session_file.exists():
        token = session_file.read_text().strip()
    elif "BW_SESSION" in os.environ:
        token = os.environ["BW_SESSION"]

    if token and _check_bw_session(token):
        return token

    password = _decrypt_age_password()
    token = _bw_unlock(password)

    session_file.parent.mkdir(parents=True, exist_ok=True)
    session_file.write_text(token)
    session_file.chmod(0o600)

    return token
