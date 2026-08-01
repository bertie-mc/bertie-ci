# bertie-ci

Local-first Minecraft checks shared by the
[`bertie-mc`](https://github.com/bertie-mc) projects.

The executable is the abstraction boundary. Artifact assembly, JVM unit tests,
GameTests, client world join, and dedicated-server readiness are separate commands that
can be composed locally or by any CI provider. GitHub Actions is only one adapter around
them.

## Run locally

From a custom mod checkout, build once, prepare each applicable side, and run the
source-agnostic probes. These lines are the Linux path; on native Windows there is no
usable Nix, so follow [`docs/windows.md`](docs/windows.md) instead.

```bash
bertie_ci_package="$(nix build github:bertie-mc/bertie-ci/v3.6.1#bertie-ci \
  --no-link --print-out-paths)"
export PATH="$bertie_ci_package/bin:$PATH"

bertie-ci build --project . --output-dir .bertie-ci/artifact
bertie-ci unit-test --project .
bertie-ci gametest --project .
bertie-ci prepare-mod-instance --project . --artifact .bertie-ci/artifact \
  --side client --output-dir .bertie-ci/client
bertie-ci client-probe --instance .bertie-ci/client/instance.json
```

`build` uses the Nix-pinned Gradle 8 executable to run `assemble`; it does not run tests.
`--output-dir` stages exactly one releaseable JAR, preserving its filename, so publishing
and runtime checks can consume the same explicit artifact. `unit-test` runs Gradle's
ordinary JVM test task independently. `gametest` runs `runGameTestServer` in NeoForge's development runtime
and fails closed unless at least one test is discovered and the GameTest server reports a
clean completion. This catches mod-loading crashes that Gradle can otherwise report as a
successful task.
`prepare-mod-instance` consumes the already-built JAR and declarative dependency
fixtures sourced from the canonical modpack. `client-probe` and `server-probe` consume
only a prepared-instance descriptor;
they do not know whether packwiz or a mod artifact produced it. The probes run:

- the HeadlessHQ `mc-runtime-test` client probe under Xvfb, which loads the real client,
  joins a singleplayer world, waits for the player's chunk, and exits;
- a HeadlessMC dedicated-server probe, which waits for server readiness and stops it
  cleanly.

Pass `--artifact path/to/mod.jar` or a directory containing one runtime JAR to prepare an
artifact downloaded from another build. Logs and crash reports remain below
`.bertie-ci/` for inspection. Minecraft downloads are cached under
`${XDG_CACHE_HOME:-~/.cache}/bertie-ci` by default.

Mods with external runtime dependencies select one or more canonical pack mods or
aggregate fixture profiles. For example:

```bash
bertie-ci prepare-mod-instance --project . --artifact .bertie-ci/artifact \
  --fixture forbidden-arcanus,irons-spells --side client \
  --output-dir .bertie-ci/client
```

The Nix lock pins an immutable `bertie-pack` checkout. A selector resolves directly to
`mods/<selector>.pw.toml` when that canonical mod exists. Explicit profiles are reserved
for aggregate dependency closures, so `profiles.json` contains no one-to-one aliases.
`bertie-ci` therefore owns only the small dependency-set mappings; mod versions, download
hashes, filenames, and physical sides have one source of truth. The official packwiz
installer resolves that metadata into each ephemeral side-specific instance. Selectors
compose by set union, so combinations do not require a new workflow or a project branch
in Python. Every client instance also gets Collective and Hide Experimental Warning from
the same canonical pack snapshot.

For example, the `artifacts` profile installs the pack's Artifacts and Curios pins for
mods such as `fart-bomb`.

From a packwiz checkout, validation never mutates the source tree. Download resolution,
side preparation, probing, and exports remain separate operations:

```bash
bertie-ci pack-validate --project .
bertie-ci pack-resolve --project . --side both --output-dir .bertie-ci/resolve
bertie-ci prepare-pack-instance --project . --side client --output-dir .bertie-ci/client
bertie-ci client-probe --instance .bertie-ci/client/instance.json --max-memory 10G
```

## GitHub Actions adapters

The command-line operations are also exposed as independent composite actions. Each job
runs `actions/setup` once; it installs Nix, builds the pinned package once, and adds the
wrapped `bertie-ci` command to `PATH`. Operational actions call that command directly and
do not reevaluate Nixpkgs.

- `bertie-mc/bertie-ci/actions/setup@v3.6.1`
- `bertie-mc/bertie-ci/actions/build@v3.6.1`
- `bertie-mc/bertie-ci/actions/unit-test@v3.6.1`
- `bertie-mc/bertie-ci/actions/gametest@v3.6.1`
- `bertie-mc/bertie-ci/actions/prepare-mod-instance@v3.6.1`
- `bertie-mc/bertie-ci/actions/prepare-pack-instance@v3.6.1`
- `bertie-mc/bertie-ci/actions/client-probe@v3.6.1`
- `bertie-mc/bertie-ci/actions/server-probe@v3.6.1`
- `bertie-mc/bertie-ci/actions/pack-validate@v3.6.1`
- `bertie-mc/bertie-ci/actions/pack-resolve@v3.6.1`
- `bertie-mc/bertie-ci/actions/pack-export-client@v3.6.1`
- `bertie-mc/bertie-ci/actions/pack-export-server@v3.6.1`
- `bertie-mc/bertie-ci/actions/github-release@v3.6.1`

Each owns one operation. Except for the GitHub-only publisher, operational actions expect
the setup action to have placed `bertie-ci` on `PATH`. The build and test actions do not
check out source, transfer artifacts, or choose job dependencies; the GitHub publisher
consumes files and never builds them. A custom workflow can compose the actions as
ordinary steps.

Small reusable workflows provide the common GitHub-specific job adapters. A repository
keeps its trigger and dependency graph visible while reusing the implementation.
GitHub requires reusable workflows to live directly in `.github/workflows`, so these
adapters cannot be moved alongside the composite actions in `workflows/`.

For example:

```yaml
name: Build and test

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  build:
    uses: bertie-mc/bertie-ci/.github/workflows/build-mod.yml@v3.6.1

  unit-test:
    uses: bertie-mc/bertie-ci/.github/workflows/unit-test.yml@v3.6.1

  gametest:
    uses: bertie-mc/bertie-ci/.github/workflows/gametest.yml@v3.6.1

  client:
    needs: build
    uses: bertie-mc/bertie-ci/.github/workflows/client.yml@v3.6.1
    with:
      artifact-name: ${{ needs.build.outputs.artifact-name }}
      fixture: forbidden-arcanus,irons-spells

  server:
    needs: build
    uses: bertie-mc/bertie-ci/.github/workflows/server.yml@v3.6.1
    with:
      artifact-name: ${{ needs.build.outputs.artifact-name }}
      fixture: forbidden-arcanus,irons-spells
```

`build-mod.yml` only assembles and uploads a JAR. `unit-test.yml` only runs ordinary JVM
tests. `client.yml` and `server.yml` only download and test the named artifact.
`gametest.yml` only runs the development-runtime suite.
`github-release.yml` only downloads and publishes a named artifact. A release therefore
composes `build-mod.yml` followed by `github-release.yml`; it has no second build recipe.

```yaml
jobs:
  build:
    uses: bertie-mc/bertie-ci/.github/workflows/build-mod.yml@v3.6.1

  publish:
    needs: build
    permissions:
      contents: write
    uses: bertie-mc/bertie-ci/.github/workflows/github-release.yml@v3.6.1
    with:
      artifact-name: ${{ needs.build.outputs.artifact-name }}
```

Test logic does not depend on GitHub-hosted runner setup or `apt-get`. The Python commands
are CI-provider-independent and avoid POSIX-shell assumptions; Nix is the supported Linux
dependency provider, while other platforms can supply Java, HeadlessHQ artifacts, and a
display backend through environment variables. On Linux, the Python runner starts and
supervises Xvfb directly; it does not depend on a distribution-specific `xvfb-run` shell
helper. On Windows the runner invokes a Gradle 8 installation directly, and every check
runs natively without WSL; [`docs/windows.md`](docs/windows.md) covers the
setup and the one behavioral difference, which is that `client` has no Xvfb equivalent and
therefore occupies the desktop session it runs on.

## GameTests are a separate layer

NeoForge intentionally registers `@GameTest` methods only in a development runtime, not
in the production installation launched by HeadlessMC. A mod that has GameTests should
compose `gametest.yml`, the `gametest` action, or the standalone command in addition to
its production client/server checks. Keeping the layers separate catches
both kinds of failure:

- Gradle GameTests exercise mod behavior in NeoForge's development runtime.
- client/server commands exercise the built artifact in exact production runtimes.

The client probe still uses `mc-runtime-test` because its world creation, player join,
chunk wait, timeout, and clean exit are exactly the reusable assertion needed here. It is
not used as a substitute for NeoForge's development-only GameTest runner.

## Pins

The initial toolchain is Minecraft 1.21.1, NeoForge 21.1.233, Gradle 8.14.4, Java 21, HeadlessMC
2.10.0, mc-runtime-test 4.5.1, and packwiz-installer 0.5.14. Third-party JARs are
fixed-output Nix inputs with verified SHA-256 hashes. The canonical `bertie-pack`
metadata source is also an immutable flake input; updating it is an explicit lock-file
change.
