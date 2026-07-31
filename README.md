# bertie-ci

Local-first Minecraft checks shared by the
[`bertie-mc`](https://github.com/bertie-mc) projects.

The executable is the abstraction boundary. Build, GameTests, client world join, and
dedicated-server readiness are separate commands that can be composed locally or by any
CI provider. GitHub Actions is only one adapter around them.

## Run locally

From a custom mod checkout, build once and run whichever checks apply:

```bash
nix run github:bertie-mc/bertie-ci/v2.0.1#bertie-ci -- build --project .
nix run github:bertie-mc/bertie-ci/v2.0.1#bertie-ci -- gametest --project .
nix run github:bertie-mc/bertie-ci/v2.0.1#bertie-ci -- client --project .
nix run github:bertie-mc/bertie-ci/v2.0.1#bertie-ci -- server --project .
```

`build` uses the repository's Gradle wrapper and leaves the releaseable JAR in
`build/libs`. `gametest` runs `runGameTestServer` in NeoForge's development runtime
and fails closed unless at least one test is discovered and the GameTest server reports a
clean completion. This catches mod-loading crashes that Gradle can otherwise report as a
successful task.
The production commands consume an already-built JAR and run:

- the HeadlessHQ `mc-runtime-test` client probe under Xvfb, which loads the real client,
  joins a singleplayer world, waits for the player's chunk, and exits;
- a HeadlessMC dedicated-server probe, which waits for server readiness and stops it
  cleanly.

Pass `--artifact path/to/mod.jar` or a directory containing one runtime JAR to test an
artifact downloaded from another build. Logs and crash reports remain below
`.bertie-ci/` for inspection. Minecraft downloads are cached under
`${XDG_CACHE_HOME:-~/.cache}/bertie-ci` by default.

Mods with external runtime dependencies select one or more declarative packwiz fixture
profiles. For example:

```bash
nix run github:bertie-mc/bertie-ci/v2.0.1#bertie-ci -- \
  client --project . --fixture forbidden-arcanus,irons-spells
```

The official packwiz installer resolves pinned metadata into each ephemeral side-specific
instance. Profiles compose by set union, so combinations do not require a new workflow or
a project branch in Python. Every client instance also gets the pinned Collective and Hide
Experimental Warning baseline; `bertie-pack` ships the same warning-hiding mod.

## GitHub Actions adapter

A repository needs only its triggers and one caller job:

```yaml
name: Build and test

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  checks:
    uses: bertie-mc/bertie-ci/.github/workflows/neoforge-mod.yml@v2.0.1
    with:
      sides: both
      gametest: true
      fixture: forbidden-arcanus,irons-spells
```

The adapter has separate build, GameTest, client, and server jobs. The build job publishes
the JAR as a workflow artifact; the production jobs download and test that exact artifact.
The GameTest job is optional because only projects with registered GameTests should pay
for a development-runtime launch. Each job invokes one of the same commands shown above.

Test logic does not depend on GitHub-hosted runner setup or `apt-get`. The Python commands
are CI-provider-independent and avoid POSIX-shell assumptions; Nix is the supported Linux
dependency provider, while other platforms can supply Java, HeadlessHQ artifacts, and a
display backend through environment variables. On Linux, the Python runner starts and
supervises Xvfb directly; it does not depend on a distribution-specific `xvfb-run` shell
helper.

## GameTests are a separate layer

NeoForge intentionally registers `@GameTest` methods only in a development runtime, not
in the production installation launched by HeadlessMC. A mod that has GameTests should
enable the reusable workflow's `gametest` input or run the standalone `gametest` command
in addition to its production client/server checks. Keeping the layers separate catches
both kinds of failure:

- Gradle GameTests exercise mod behavior in NeoForge's development runtime.
- client/server commands exercise the built artifact in exact production runtimes.

The client probe still uses `mc-runtime-test` because its world creation, player join,
chunk wait, timeout, and clean exit are exactly the reusable assertion needed here. It is
not used as a substitute for NeoForge's development-only GameTest runner.

## Pins

The initial toolchain is Minecraft 1.21.1, NeoForge 21.1.217, Java 21, HeadlessMC
2.10.0, mc-runtime-test 4.5.1, and packwiz-installer 0.5.14. Third-party JARs are
fixed-output Nix inputs with verified SHA-256 hashes.

The staged rollout, dependency-fixture design, and modpack testing levels are documented
in [`docs/rollout-plan.md`](docs/rollout-plan.md).
