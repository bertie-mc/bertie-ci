from __future__ import annotations

import shutil
from pathlib import Path


def _runtime_jars(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.glob("*.jar")
        if not path.name.endswith(("-sources.jar", "-javadoc.jar"))
    )


def find_artifact(project: Path, requested: Path | None) -> Path:
    location = project / "build" / "libs" if requested is None else requested
    if not location.is_absolute():
        location = project / location
    location = location.resolve(strict=True)

    if location.is_file():
        return location
    if not location.is_dir():
        raise RuntimeError(f"Artifact is neither a file nor directory: {location}")

    artifacts = _runtime_jars(location)
    if len(artifacts) != 1:
        raise RuntimeError(
            f"Expected one runtime JAR in {location}, found {len(artifacts)}; "
            "use --artifact with an exact file"
        )
    return artifacts[0].resolve(strict=True)


def stage_artifact(
    artifact: Path, output_dir: Path, filename: str | None = None
) -> Path:
    artifact = artifact.resolve(strict=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_dir = output_dir.resolve(strict=True)
    if output_dir == artifact.parent:
        raise RuntimeError("Artifact output directory must differ from build/libs")

    destination = output_dir / (filename or artifact.name)
    unexpected = [path for path in output_dir.glob("*.jar") if path != destination]
    if unexpected:
        names = ", ".join(path.name for path in unexpected)
        raise RuntimeError(f"Artifact output directory contains other JARs: {names}")
    return Path(shutil.copy2(artifact, destination)).resolve(strict=True)
