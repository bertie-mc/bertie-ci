# bertie-ci

Local-first Minecraft runtime checks shared by the
[`bertie-mc`](https://github.com/bertie-mc) projects.

The executable is the abstraction boundary. GitHub Actions is only one adapter around
it, so the same build, exact-loader install, world join, and dedicated-server readiness
checks can be reproduced on a headless development machine.

## Run locally

From a custom mod checkout:

```bash
nix run github:bertie-mc/bertie-ci#bertie-ci -- \
  mod --project . --sides both
```

The command builds with the repository's Gradle wrapper, stages the runtime JAR in an
ignored `.bertie-ci/` directory, installs the exact shared NeoForge build, and runs:

- the HeadlessHQ `mc-runtime-test` client probe under Xvfb, which loads the real client,
  joins a singleplayer world, waits for the player's chunk, and exits;
- a HeadlessMC dedicated-server probe, which waits for server readiness and stops it
  cleanly.

Use `--sides client` or `--sides server` to run one side. Logs and crash reports remain below
`.bertie-ci/` for inspection. Minecraft downloads are cached under
`${XDG_CACHE_HOME:-~/.cache}/bertie-ci` by default.

## GitHub Actions adapter

A repository needs only its triggers and one caller job:

```yaml
name: Build and runtime

on:
  push:
    branches: ["main"]
  pull_request:
    branches: ["main"]

jobs:
  runtime:
    uses: bertie-mc/bertie-ci/.github/workflows/neoforge-mod.yml@main
    with:
      sides: both
```

The adapter installs Nix and invokes the same command shown above. Test logic does not
depend on GitHub-hosted runner setup or `apt-get`. The Python command itself is
CI-provider-independent and avoids POSIX-shell assumptions; Nix is the supported Linux
dependency provider, while other platforms can supply Java, HeadlessHQ artifacts, and a
display backend through environment variables. On Linux, the Python runner starts and
supervises Xvfb directly; it does not depend on a distribution-specific `xvfb-run`
shell helper.

## GameTests are a separate layer

NeoForge intentionally registers `@GameTest` methods only in a development runtime,
not in the production installation launched by HeadlessMC. A mod that has GameTests
should therefore run its Gradle `runGameTestServer` task in addition to this production
client/server smoke test. Keeping the layers separate catches both kinds of failure:

- Gradle GameTests exercise mod behavior in NeoForge's development runtime.
- `bertie-ci` exercises the built artifact in an exact production client and server.

The client probe still uses `mc-runtime-test` because its world creation, player join,
chunk wait, timeout, and clean exit are exactly the reusable assertion needed here. It
is not used as a substitute for NeoForge's development-only GameTest runner.

## Pins

The initial toolchain is Minecraft 1.21.1, NeoForge 21.1.217, Java 21, HeadlessMC
2.10.0, and mc-runtime-test 4.5.1. Third-party JARs are fixed-output Nix inputs with
verified SHA-256 hashes.

The staged rollout, dependency-fixture design, and modpack testing levels are documented
in [`docs/rollout-plan.md`](docs/rollout-plan.md).
