import os
import shutil
import subprocess
from pathlib import Path

import pytest

from bertie_ci.properties import render_properties, write_properties

WINDOWS_JAVA = r"C:\Program Files\Eclipse Adoptium\jdk-21\bin\java.exe"
WINDOWS_GAMEDIR = r"C:\Users\berlord\ci\run"

PROBE = """
import java.io.*;
import java.util.Properties;

public class Probe {
    public static void main(String[] args) throws IOException {
        Properties properties = new Properties();
        try (InputStream in = new FileInputStream(args[0])) {
            properties.load(in);
        }
        PrintStream out = new PrintStream(System.out, true, "UTF-8");
        for (String key : new java.util.TreeSet<>(properties.stringPropertyNames())) {
            out.println(key + "\\t" + properties.getProperty(key));
        }
    }
}
"""


def _java() -> str | None:
    home = os.environ.get("BERTIE_CI_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if home:
        candidate = Path(home) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if candidate.is_file():
            return os.fspath(candidate)
    return shutil.which("java")


def _load_with_java(properties: Path, tmp_path: Path) -> dict[str, str]:
    java = _java()
    if java is None:
        pytest.skip("Java is unavailable")
    probe = tmp_path / "Probe.java"
    probe.write_text(PROBE, encoding="utf-8")
    result = subprocess.run(
        [java, "-Dstdout.encoding=UTF-8", os.fspath(probe), os.fspath(properties)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    return dict(
        line.split("\t", 1) for line in result.stdout.splitlines() if "\t" in line
    )


def test_backslashes_are_escaped() -> None:
    rendered = render_properties({"hmc.gamedir": WINDOWS_GAMEDIR})

    assert rendered == "hmc.gamedir=C:\\\\Users\\\\berlord\\\\ci\\\\run\n"


def test_value_separators_are_left_alone() -> None:
    rendered = render_properties({"hmc.jvmargs": "-Xmx4G -DFoo=0"})

    assert rendered == "hmc.jvmargs=-Xmx4G -DFoo=0\n"


def test_non_ascii_is_escaped_to_ascii(tmp_path: Path) -> None:
    target = tmp_path / "config.properties"

    write_properties(target, {"hmc.gamedir": "C:\\Users\\Jos\u00e9\\run"})

    assert target.read_text(encoding="ascii") == (
        "hmc.gamedir=C:\\\\Users\\\\Jos\\u00e9\\\\run\n"
    )


def test_astral_characters_become_surrogate_pairs() -> None:
    rendered = render_properties({"hmc.gamedir": "C:\\\U0001f600"})

    assert rendered == "hmc.gamedir=C:\\\\\\ud83d\\ude00\n"


def test_leading_space_and_comment_markers_are_escaped() -> None:
    rendered = render_properties({"hmc.gamedir": " lead", "hmc.mcdir": "#hash"})

    assert rendered == "hmc.gamedir=\\ lead\nhmc.mcdir=\\#hash\n"


def test_java_reads_windows_paths_back_verbatim(tmp_path: Path) -> None:
    target = tmp_path / "config.properties"
    entries = {
        "hmc.java.versions": WINDOWS_JAVA,
        "hmc.gamedir": WINDOWS_GAMEDIR,
        # A segment starting with a lowercase "u" makes an unescaped file throw
        # "Malformed \\uxxxx encoding" rather than merely lose its separators.
        "hmc.mcdir": r"C:\users\berlord\cache",
        "hmc.jvmargs": "-Xms512M -Xmx4G -DMcRuntimeGameTestMinExpectedGameTests=0",
    }
    write_properties(target, entries)

    assert _load_with_java(target, tmp_path) == entries


def test_java_rejects_the_unescaped_form_we_used_to_write(tmp_path: Path) -> None:
    """Pin the defect this module exists to prevent."""
    target = tmp_path / "config.properties"
    target.write_text(f"hmc.mcdir={WINDOWS_GAMEDIR}\n", encoding="utf-8")

    loaded = _load_with_java(target, tmp_path)

    assert loaded["hmc.mcdir"] != WINDOWS_GAMEDIR
