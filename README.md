# bertie-ci

Local-first Minecraft checks shared by the
[`bertie-mc`](https://github.com/bertie-mc) projects.

The executable is the abstraction boundary. It owns tool setup, instance assembly,
process supervision and result collection. Projects own their test suites and decide
which runners apply to them. Artifact assembly, JVM tests, GameTests and production
runtime tests remain separate commands that can be composed locally or by any CI
provider. GitHub Actions is only one adapter around them.

## Run locally

From a custom mod checkout, build once and run the project's applicable suites. These
lines are the Linux path; on native Windows there is no usable Nix, so follow
[`docs/windows.md`](docs/windows.md) instead.

```bash
bertie_ci_package="$(nix build github:bertie-mc/bertie-ci/v3.7.2#bertie-ci \
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
only a prepared-instance descriptor; they do not know whether packwiz or a mod artifact
produced it. They are reusable opt-in smoke presets:

- the HeadlessHQ `mc-runtime-test` client probe under Xvfb, which loads the real client,
  joins a singleplayer world, waits for the player's chunk, and exits;
- a HeadlessMC dedicated-server probe, which waits for server readiness and stops it
  cleanly.

Those presets are not a project's integration suite. A project that needs a production
client test supplies a test-only mod containing its own assertions. The suite can use
GameTests, an exact project-owned success marker, or both:

```bash
bertie-ci client-test --instance .bertie-ci/client/instance.json \
  --test-mod build/test-libs/example-client-tests.jar \
  --require-log EXAMPLE_CLIENT_ASSERTIONS_PASSED
```

`mc-runtime-test` creates and joins the world. The test-only mod owns the assertions and
emits its stable marker only after they pass; `bertie-ci` fails closed if the marker is
absent. Structure-backed suites can additionally use `--minimum-game-tests`; their NBT
fixtures belong under the project's test resource source set, never in the release JAR.
A project-specific dedicated-server
suite supplies a HeadlessMC command-test document instead:

```bash
bertie-ci server-test --instance .bertie-ci/server/instance.json \
  --command-test tests/runtime/server.json
```

The JSON and its expected messages live in the project. `bertie-ci` only installs and
supervises the exact server. Ordinary JVM tests and the development GameTest server are
usually cheaper and should be preferred whenever they can express the behavior.

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

- `bertie-mc/bertie-ci/actions/setup@v3.7.2`
- `bertie-mc/bertie-ci/actions/build@v3.7.2`
- `bertie-mc/bertie-ci/actions/unit-test@v3.7.2`
- `bertie-mc/bertie-ci/actions/gametest@v3.7.2`
- `bertie-mc/bertie-ci/actions/prepare-mod-instance@v3.7.2`
- `bertie-mc/bertie-ci/actions/prepare-pack-instance@v3.7.2`
- `bertie-mc/bertie-ci/actions/client-test@v3.7.2`
- `bertie-mc/bertie-ci/actions/server-test@v3.7.2`
- `bertie-mc/bertie-ci/actions/client-probe@v3.7.2`
- `bertie-mc/bertie-ci/actions/server-probe@v3.7.2`
- `bertie-mc/bertie-ci/actions/pack-validate@v3.7.2`
- `bertie-mc/bertie-ci/actions/pack-resolve@v3.7.2`
- `bertie-mc/bertie-ci/actions/pack-export-client@v3.7.2`
- `bertie-mc/bertie-ci/actions/pack-export-server@v3.7.2`
- `bertie-mc/bertie-ci/actions/github-release@v3.7.2`

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
    uses: bertie-mc/bertie-ci/.github/workflows/build-mod.yml@v3.7.2

  unit-test:
    uses: bertie-mc/bertie-ci/.github/workflows/unit-test.yml@v3.7.2

  gametest:
    uses: bertie-mc/bertie-ci/.github/workflows/gametest.yml@v3.7.2

  client:
    needs: build
    uses: bertie-mc/bertie-ci/.github/workflows/client.yml@v3.7.2
    with:
      artifact-name: ${{ needs.build.outputs.artifact-name }}
      fixture: forbidden-arcanus,irons-spells

  server:
    needs: build
    uses: bertie-mc/bertie-ci/.github/workflows/server.yml@v3.7.2
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
    uses: bertie-mc/bertie-ci/.github/workflows/build-mod.yml@v3.7.2

  publish:
    needs: build
    permissions:
      contents: write
    uses: bertie-mc/bertie-ci/.github/workflows/github-release.yml@v3.7.2
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

## Projects choose their layers

NeoForge intentionally registers ordinary `@GameTest` methods only in a development
runtime, not in the production installation launched by HeadlessMC. A mod with server or
world behavior should normally compose `gametest.yml`, the `gametest` action, or the
standalone command. A production runtime test is added only when it covers a different
risk, such as client rendering, side safety, optional-mod loading, or release-JAR
packaging.

`client-test` still uses `mc-runtime-test` because client launch, world creation, player
join, timeouts and clean exit are reusable mechanics. Assertions stay in the project and
can run at the lifecycle point appropriate to the behavior instead of being forced into
a GameTest. `client-probe` is merely the explicit zero-assertion world-join preset.

## Pins

The initial toolchain is Minecraft 1.21.1, NeoForge 21.1.233, Gradle 8.14.4, Java 21, HeadlessMC
2.10.0, mc-runtime-test 4.5.1, and packwiz-installer 0.5.14. Third-party JARs are
fixed-output Nix inputs with verified SHA-256 hashes. The canonical `bertie-pack`
metadata source is also an immutable flake input; updating it is an explicit lock-file
change.
