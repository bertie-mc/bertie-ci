from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from .artifact import find_artifact, stage_artifact
from .config import (
    load_client_runtime_tools,
    load_fixture_tools,
    load_java,
    load_pack_tools,
    load_packwiz,
    load_packwiz_installer,
    load_server_runtime_tools,
    load_versions,
)
from .gradle import (
    assemble_client_test_mod,
    assemble_mod,
    run_gametests,
    run_unit_tests,
)
from .instance import (
    load_instance,
    prepare_mod_instance,
    prepare_pack_instance,
)
from .pack import export_client_pack, export_server_pack, validate_pack
from .runtime import RuntimeContext, run_client_test, run_server_test


def _add_project(
    parser: argparse.ArgumentParser, help_text: str = "project checkout"
) -> None:
    parser.add_argument("--project", type=Path, default=Path.cwd(), help=help_text)


def _add_fixture(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--fixture",
        action="append",
        default=[],
        help=(
            "comma-separated canonical mod names or aggregate fixture profiles; "
            "may be repeated"
        ),
    )


def _memory(value: str) -> str:
    if not re.fullmatch(r"[1-9][0-9]*[mMgG]", value):
        raise argparse.ArgumentTypeError("memory must look like 4G or 1024M")
    return value.upper()


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value cannot be negative")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def _optional_path(value: str) -> Path | None:
    """Translate an empty adapter input into an omitted optional path."""
    return Path(value) if value else None


def _add_runtime(
    parser: argparse.ArgumentParser, default_timeout: int, default_memory: str
) -> None:
    parser.add_argument("--instance", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument(
        "--timeout", type=_positive_int, default=default_timeout, metavar="SECONDS"
    )
    parser.add_argument("--max-memory", type=_memory, default=default_memory)


def _add_test_extensions(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--test-mod",
        action="append",
        default=[],
        type=_optional_path,
        metavar="JAR",
        help=(
            "optional test-only mod JAR or directory containing one JAR; "
            "may be repeated"
        ),
    )
    parser.add_argument(
        "--require-log",
        action="append",
        default=[],
        metavar="TEXT",
        help="fail unless the runtime log contains this exact text; may be repeated",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bertie-ci",
        description="Composable local-first checks for bertie-mc projects",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    build = subcommands.add_parser("build", help="build a NeoForge mod JAR")
    _add_project(build, "mod checkout")
    build.add_argument(
        "--output-dir",
        type=Path,
        help="copy the single releaseable JAR into this artifact directory",
    )

    build_client_test_mod = subcommands.add_parser(
        "build-client-test-mod",
        help="build and stage the test-only mod from the clientTest source set",
    )
    _add_project(build_client_test_mod, "mod checkout")
    build_client_test_mod.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".bertie-ci/client-test-mod"),
        help="directory for the staged client-test-mod.jar",
    )

    unit_test = subcommands.add_parser(
        "unit-test", help="run the mod's ordinary JVM unit tests"
    )
    _add_project(unit_test, "mod checkout")

    gametest = subcommands.add_parser(
        "gametest", help="run NeoForge GameTests in the Gradle development runtime"
    )
    _add_project(gametest, "mod checkout")
    gametest.add_argument("--work-dir", type=Path)
    gametest.add_argument(
        "--timeout", type=_positive_int, default=15 * 60, metavar="SECONDS"
    )

    prepare_mod = subcommands.add_parser(
        "prepare-mod-instance",
        help="assemble a side-specific instance around a built mod",
    )
    _add_project(prepare_mod, "mod checkout")
    prepare_mod.add_argument("--artifact", type=Path)
    _add_fixture(prepare_mod)
    prepare_mod.add_argument("--side", choices=("client", "server"), required=True)
    prepare_mod.add_argument("--output-dir", type=Path, required=True)

    prepare_pack = subcommands.add_parser(
        "prepare-pack-instance", help="install one side of a canonical packwiz pack"
    )
    _add_project(prepare_pack, "packwiz checkout")
    prepare_pack.add_argument("--side", choices=("client", "server"), required=True)
    prepare_pack.add_argument("--output-dir", type=Path, required=True)

    client_test = subcommands.add_parser(
        "client-test",
        help="run the world-join scenario and optional extensions in a prepared client",
    )
    _add_runtime(client_test, 25 * 60, "4G")
    _add_test_extensions(client_test)
    client_test.add_argument(
        "--minimum-game-tests",
        type=_nonnegative_int,
        default=0,
        metavar="COUNT",
        help="fail unless mc-runtime-test discovers at least this many GameTests",
    )

    server_test = subcommands.add_parser(
        "server-test",
        help="run readiness or a project-owned scenario in a prepared server",
    )
    _add_runtime(server_test, 15 * 60, "3G")
    _add_test_extensions(server_test)
    server_test.add_argument(
        "--command-test",
        type=_optional_path,
        metavar="JSON",
        help="optional project-owned HeadlessMC command-test specification",
    )

    pack_validate = subcommands.add_parser(
        "pack-validate", help="validate a packwiz checkout without modifying it"
    )
    _add_project(pack_validate, "packwiz checkout")

    pack_export_client = subcommands.add_parser(
        "pack-export-client", help="export a Modrinth client pack"
    )
    _add_project(pack_export_client, "packwiz checkout")
    pack_export_client.add_argument("--output", type=Path, required=True)

    pack_export_server = subcommands.add_parser(
        "pack-export-server", help="export a no-mod-JAR server installer archive"
    )
    _add_project(pack_export_server, "packwiz checkout")
    pack_export_server.add_argument("--output", type=Path, required=True)

    return parser


def _project(args: argparse.Namespace) -> Path:
    return args.project.resolve(strict=True)


def _under_project(project: Path, path: Path) -> Path:
    return path.resolve() if path.is_absolute() else (project / path).resolve()


def _cache(path: Path | None) -> Path:
    default = (
        Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "bertie-ci"
    )
    if path is None:
        return default.resolve()
    return path.resolve()


def _fixture_profiles(values: list[str]) -> list[str]:
    return [
        name.strip() for value in values for name in value.split(",") if name.strip()
    ]


def _run_build(args: argparse.Namespace) -> None:
    project = _project(args)
    java = load_java()
    assemble_mod(project, java.parent.parent)
    artifact = find_artifact(project, None)
    if args.output_dir is not None:
        artifact = stage_artifact(artifact, _under_project(project, args.output_dir))
    print(f"Built artifact: {artifact}", flush=True)


def _run_build_client_test_mod(args: argparse.Namespace) -> None:
    project = _project(args)
    java = load_java()
    artifact = assemble_client_test_mod(
        project,
        java.parent.parent,
        _under_project(project, args.output_dir),
    )
    print(f"Built client test mod: {artifact}", flush=True)


def _run_gametest(args: argparse.Namespace) -> None:
    project = _project(args)
    work = _under_project(project, args.work_dir or Path(".bertie-ci"))
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


def _runtime_context(
    descriptor: Path, work: Path | None, cache: Path | None, side: str
) -> RuntimeContext:
    descriptor = descriptor.resolve(strict=True)
    instance = load_instance(descriptor)
    if instance.side != side:
        raise RuntimeError(
            f"{side} test cannot consume a {instance.side} prepared instance"
        )
    runtime_work = (work or descriptor.parent).resolve()
    runtime_cache = _cache(cache)
    runtime_cache.mkdir(parents=True, exist_ok=True)
    tools = (
        load_client_runtime_tools() if side == "client" else load_server_runtime_tools()
    )
    return RuntimeContext(runtime_work, runtime_cache, instance, load_versions(), tools)


def _run_test(args: argparse.Namespace, side: str) -> None:
    context = _runtime_context(args.instance, args.work_dir, args.cache_dir, side)
    test_mods = tuple(path.resolve() for path in args.test_mod if path is not None)
    required_log_markers = tuple(marker for marker in args.require_log if marker)
    if side == "client":
        run_client_test(
            context,
            args.timeout,
            args.max_memory,
            minimum_game_tests=args.minimum_game_tests,
            test_mods=test_mods,
            required_log_markers=required_log_markers,
        )
    else:
        run_server_test(
            context,
            args.timeout,
            args.max_memory,
            command_test=args.command_test,
            test_mods=test_mods,
            required_log_markers=required_log_markers,
        )


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
            case "build-client-test-mod":
                _run_build_client_test_mod(args)
            case "unit-test":
                _run_unit_test(args)
            case "gametest":
                _run_gametest(args)
            case "prepare-mod-instance":
                project = _project(args)
                artifact = args.artifact
                if artifact is not None and not artifact.is_absolute():
                    artifact = project / artifact
                descriptor = prepare_mod_instance(
                    project,
                    artifact,
                    _fixture_profiles(args.fixture),
                    args.side,
                    _under_project(project, args.output_dir),
                    load_versions(),
                    load_fixture_tools(),
                )
                print(f"Prepared instance: {descriptor}", flush=True)
            case "prepare-pack-instance":
                project = _project(args)
                descriptor = prepare_pack_instance(
                    project,
                    args.side,
                    _under_project(project, args.output_dir),
                    load_pack_tools(),
                )
                print(f"Prepared instance: {descriptor}", flush=True)
            case "client-test" | "server-test":
                _run_test(args, args.command.removesuffix("-test"))
            case "pack-validate":
                summary = validate_pack(_project(args), load_packwiz())
                print(
                    "Pack valid: "
                    f"{summary.metafiles} metafiles "
                    f"({summary.client} client, {summary.server} server, {summary.both} both), "
                    f"{summary.config_files} config files",
                    flush=True,
                )
            case "pack-export-client":
                project = _project(args)
                output = export_client_pack(
                    project, _under_project(project, args.output), load_packwiz()
                )
                print(f"Exported client pack: {output}", flush=True)
            case "pack-export-server":
                project = _project(args)
                output = export_server_pack(
                    project,
                    _under_project(project, args.output),
                    load_packwiz_installer(),
                )
                print(f"Exported server pack: {output}", flush=True)
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"bertie-ci: {error}\n")


if __name__ == "__main__":
    main()
