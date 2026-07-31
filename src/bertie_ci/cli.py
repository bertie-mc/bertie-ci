from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

from .config import load_tools, load_versions
from .runtime import Context, build_mod, find_artifact, run_client, run_server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Local-first runtime checks for bertie-mc projects"
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    mod = subcommands.add_parser(
        "mod", help="build and runtime-test a custom NeoForge mod"
    )
    mod.add_argument("--project", type=Path, default=Path.cwd(), help="mod checkout")
    mod.add_argument("--sides", choices=("client", "server", "both"), default="both")
    mod.add_argument("--artifact", type=Path)
    mod.add_argument("--work-dir", type=Path)
    mod.add_argument("--cache-dir", type=Path)
    mod.add_argument("--no-build", action="store_true")
    mod.add_argument("--client-timeout", type=int, default=25 * 60, metavar="SECONDS")
    mod.add_argument("--server-timeout", type=int, default=15 * 60, metavar="SECONDS")
    return parser


def _run_mod(args: argparse.Namespace) -> None:
    project = args.project.resolve(strict=True)
    work = (args.work_dir or project / ".bertie-ci").resolve()
    cache_default = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "bertie-ci"
    )
    cache = (args.cache_dir or cache_default).resolve()
    work.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    versions = load_versions()
    tools = load_tools()
    java_home = tools.java.parent.parent
    if not args.no_build:
        build_mod(project, java_home)
    artifact = find_artifact(project, args.artifact)
    context = Context(project, work, cache, artifact, versions, tools)
    print(f"Using mod artifact: {artifact}")
    print(f"Runtime directory: {work}")
    print(f"Minecraft cache: {cache}")

    if args.sides in ("client", "both"):
        run_client(context, args.client_timeout)
    if args.sides in ("server", "both"):
        run_server(context, args.server_timeout)


def main() -> None:
    parser = _parser()
    args = parser.parse_args()
    try:
        if args.command == "mod":
            _run_mod(args)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"bertie-ci: {error}\n")


if __name__ == "__main__":
    main()
