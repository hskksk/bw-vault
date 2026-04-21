import os
import sys

from .bw_session import ensure_bw_session
from .config import get_profile, load_config
from .vault import resolve_fields


def cmd_exec(args: list[str]) -> None:
    profile = "default"
    cmd: list[str] = []

    if args and args[0] != "--":
        profile = args[0]
        args = args[1:]
    if args and args[0] == "--":
        cmd = args[1:]

    config = load_config()
    fields = get_profile(config, profile)

    env_vars = resolve_fields(fields)
    env = {**os.environ, **env_vars}

    if not cmd:
        shell = os.environ.get("SHELL", "/bin/sh")
        os.execvpe(shell, [shell], env)
    else:
        os.execvpe(cmd[0], cmd, env)


def cmd_run(args: list[str]) -> None:
    if not args:
        print("Usage: bw-vault run <command> [args...]", file=sys.stderr)
        sys.exit(1)

    bw_session = ensure_bw_session()
    env = {**os.environ, "BW_SESSION": bw_session}
    os.execvpe(args[0], args, env)


def main() -> None:
    argv = sys.argv[1:]

    if not argv:
        _usage()
        sys.exit(1)

    command, *rest = argv

    if command == "exec":
        cmd_exec(rest)
    elif command == "run":
        cmd_run(rest)
    else:
        _usage()
        sys.exit(1)


def _usage() -> None:
    print("Usage: bw-vault exec [<profile>] [-- <command> [args...]]", file=sys.stderr)
    print("       bw-vault run <command> [args...]", file=sys.stderr)
