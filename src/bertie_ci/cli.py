from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from .artifact import find_artifact, stage_artifact
from .config import load_java, load_tools, load_versions
from .gradle import assemble_mod, run_gametests, run_unit_tests
from .runtime import Context, run_client, run_server


def _add_project(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", type=Path, default=Path.cwd(), help="mod checkout")


def _add_runtime(parser: argparse.ArgumentParser, default_timeout: int) -> None:
    _add_project(parser)
    parser.add_argument(
        "--artifact",
        type=Path,
        help="runtime JAR or a directory containing exactly one runtime JAR",
    )
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        help="comma-separated fixture profiles; may be repeated",
    )
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument(
        "--timeout", type=int, default=default_timeout, metavar="SECONDS"
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bertie-ci",
        description="Composable local-first checks for bertie-mc projects",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build", help="build a NeoForge mod JAR")
    _add_project(build)
    build.add_argument(
        "--output-dir",
        type=Path,
        help="copy the single releaseable JAR into this artifact directory",
    )

    unit_test = subcommands.add_parser(
        "unit-test", help="run the mod's ordinary JVM unit tests"
    )
    _add_project(unit_test)

    gametest = subcommands.add_parser(
        "gametest", help="run NeoForge GameTests in the Gradle development runtime"
    )
    _add_project(gametest)
    gametest.add_argument("--work-dir", type=Path)
    gametest.add_argument("--timeout", type=int, default=15 * 60, metavar="SECONDS")

    client = subcommands.add_parser(
        "client", help="test a built JAR with the client world-join probe"
    )
    _add_runtime(client, 25 * 60)

    server = subcommands.add_parser(
        "server", help="test a built JAR with the dedicated-server readiness probe"
    )
    _add_runtime(server, 15 * 60)
    return parser


def _project(args: argparse.Namespace) -> Path:
    return args.project.resolve(strict=True)


def _run_build(args: argparse.Namespace) -> None:
    project = _project(args)
    java = load_java()
    assemble_mod(project, java.parent.parent)
    artifact = find_artifact(project, None)
    if args.output_dir is not None:
        output_dir = args.output_dir
        if not output_dir.is_absolute():
            output_dir = project / output_dir
        output_dir = output_dir.resolve()
        artifact = stage_artifact(artifact, output_dir)
    print(f"Built artifact: {artifact}", flush=True)


def _run_gametest(args: argparse.Namespace) -> None:
    project = _project(args)
    work = (args.work_dir or project / ".bertie-ci").resolve()
    java = load_java()
    count = run_gametests(project, java.parent.parent, work, args.timeout)
    print(
        f"NeoForge GameTests passed: {count} test(s). Logs: {work / 'gametest.log'}",
        flush=True,
    )


def _run_unit_test(args: argparse.Namespace) -> None:
    project = _project(args)
    java = load_java()
    run_unit_tests(project, java.parent.parent)
    print("JVM unit tests passed.", flush=True)


def _fixture_profiles(values: list[str]) -> list[str]:
    return [
        name.strip() for value in values for name in value.split(",") if name.strip()
    ]


def _run_runtime(args: argparse.Namespace, side: str) -> None:
    project = _project(args)
    work = (args.work_dir or project / ".bertie-ci").resolve()
    cache_default = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "bertie-ci"
    )
    cache = (args.cache_dir or cache_default).resolve()
    work.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)

    artifact = find_artifact(project, args.artifact)
    context = Context(work, cache, artifact, load_versions(), load_tools())
    profiles = _fixture_profiles(args.fixture)
    print(f"Using mod artifact: {artifact}", flush=True)
    print(f"Runtime directory: {work}", flush=True)
    print(f"Minecraft cache: {cache}", flush=True)

    if side == "client":
        run_client(context, profiles, args.timeout)
    else:
        run_server(context, profiles, args.timeout)


def tolerate_unencodable_output() -> None:
    """Never let mirrored subprocess output kill a run.

    Minecraft logs carry characters the Windows ANSI code page cannot encode, and
    a redirected stdout on Windows uses that code page rather than UTF-8. The
    unabridged text is always kept in the run's log file, which is UTF-8.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main() -> None:
    tolerate_unencodable_output()
    parser = _parser()
    args = parser.parse_args()
    try:
        match args.command:
            case "build":
                _run_build(args)
            case "unit-test":
                _run_unit_test(args)
            case "gametest":
                _run_gametest(args)
            case "client" | "server":
                _run_runtime(args, args.command)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"bertie-ci: {error}\n")


if __name__ == "__main__":
    main()
