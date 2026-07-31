# Headless runtime-test rollout

## Decisions

`bertie-ci` is the test product. Its build, unit-test, GameTest, client, and server
commands are independent operations. Small composite actions map one-to-one to those
commands. Small reusable job workflows add only checkout or artifact transport;
repository workflows retain their dependency graph. The runtime code stays in Python so
process management, timeouts, paths, and Windows-specific Gradle launching are not
encoded in shell scripts.

The two production probes are deliberately small and stable:

- **Client:** launch the exact NeoForge production client under a real OpenGL context,
  create an integrated world, join it, wait for the player chunk, then exit cleanly.
- **Server:** launch the exact NeoForge production dedicated server, wait for its ready
  state, then stop it cleanly.

HeadlessMC provides exact loader installation and process lifecycle management.
`mc-runtime-test` provides the client world-join assertion. Its GitHub Action is not the
abstraction boundary because that action installs a loader dynamically and cannot pin
the exact NeoForge build used by the projects.

NeoForge `@GameTest` registration is disabled in production distributions. GameTests
therefore remain a separate behavioral layer run by Gradle's development runtime. JVM
tests, a runtime world join, and a GameTest run cover different failure modes and do not
replace one another.

## Custom-mod rollout

1. Use `bertie-tiers` as the pilot for separate client and server commands. It has no
   required external runtime mod, so failures exercise only the shared machinery.
2. Move the other self-contained mods to the reusable workflow in small batches. Use
   `client` for physically client-only mods and `both` for common mods.
3. Add a generic fixture input before moving mods with required runtime dependencies.
   Fixture selection must be declarative data; the runner must not grow branches named
   after individual projects.
4. Represent fixtures as small packwiz packs generated from a central dependency
   catalog. Pin the packwiz installer in Nix, serve the generated pack from Python on
   loopback, and let packwiz-installer resolve the requested client or server side into
   the ephemeral runtime directory. Do not implement another CurseForge/Modrinth
   downloader in `bertie-ci`.
5. Assemble the JAR without tests, run JVM unit tests and Gradle GameTests as separate
   jobs, and feed the built JAR artifact to separate production probes. No test command
   silently rebuilds the production artifact it was asked to verify.

All 21 custom NeoForge mods compose shared build and runtime jobs. The original 20 use
`v3.1.1`; `primitive-refined` uses `v3.2.1`, which adds its Create fixture and aligns the
production runtime with the pack's NeoForge 21.1.233 pin. Three physically client-only
projects omit the server job; common projects compose both. Dependency-bearing mods use
the declarative `create`, `fdlib`, `forbidden-arcanus`, `ftb-filters`, `irons-spells`,
`immersive-armors`, `rustic-engineer`, and `simply-swords` profiles. Only the two projects that currently
contain registered GameTests compose the separate GameTest job. The three projects with
JVM test sources compose the separate unit-test job. Release workflows compose the same
assembly job with an artifact-only GitHub publisher.

## Modpack strategy

Packwiz has one index per `pack.toml`; it models physical sides and optional files, but
does not provide composable modules or index inheritance. Marking large parts of the
shipping pack optional just to obtain test partitions would change product semantics and
is not an appropriate test abstraction.

Use three levels instead:

1. **Per-change metadata check:** refresh the canonical packwiz index and verify there is
   no diff. This is fast and runs on every change.
2. **Diagnostic component profiles:** maintain a small `bertie-ci-pack.toml` alongside
   the canonical pack. It assigns canonical index paths to a few coarse groups such as
   foundation, world generation, content, and client presentation. Python generates
   temporary derived indexes; no `.pw.toml` file or downloaded JAR is copied into source
   control. Profiles are useful for locating a bad cluster, not proof that the assembled
   pack works.
3. **Full-pack contract:** install the canonical pack separately for `client` and
   `server`, then run the same production world-join/readiness probes. Initially make
   this scheduled and manually dispatchable, plus run it on relevant pack changes. Once
   duration and caching are understood, decide whether it is suitable as a required pull
   request check.

The full client assertion should be world join, not title-menu detection. World join is
independent of title-screen replacements and proves resource reload, integrated-server
startup, world generation, player login, and rendering. The timeout remains an explicit
failure boundary for hidden dialogs or loading screens.

### Prepared-instance implementation

Use a prepared instance as the boundary between assembly and assertions. Do not add a
`--pack` branch to the existing mod-artifact runner and do not make one action build,
install, and test everything.

1. Add `pack-validate`, which refreshes a temporary copy of a pack and checks metadata
   without modifying the checkout. Keep download resolution as a separate operation.
2. Add `prepare-mod-instance` and `prepare-pack-instance`. Each writes a side-specific
   instance plus a small machine-readable descriptor containing the exact Minecraft and
   loader versions. Mod preparation installs fixture profiles and the built artifact;
   pack preparation installs the canonical packwiz manifest.
3. Make `client-probe` and `server-probe` consume only that descriptor and instance.
   They contain no knowledge of Gradle artifacts, fixture catalogs, or packwiz source
   trees. Both preparation paths therefore exercise the same HeadlessHQ assertions.
4. Expose those commands as one-purpose composite actions. GitHub reusable workflows may
   compose checkout and artifact transport, but the same commands remain directly usable
   from Nix or another CI provider.
5. Add separate `pack-export-client` and `pack-export-server` commands and actions.
   Release publication consumes their artifacts; it neither rebuilds nor reimplements
   either exporter.
6. Replace the pack's shell-heavy validation, client, server, and release workflows only
   after the local commands pass. Keep the canonical client/server probes scheduled and
   manually dispatchable until their timing is stable, then decide which should gate pull
   requests.

The first completed client experiment installed the pack quickly and reported that the
game itself took 122.73 seconds to start. Its 83-minute duration was a timeout on
WorldWeaver's first-run screen, not 83 minutes of mod loading. The pack now ships the
normal WorldWeaver client configuration that suppresses that wizard and disables its
network update checks. This makes the canonical full-pack world join the next useful
measurement; diagnostic component profiles can wait until a real runtime or debugging
cost demonstrates that they are needed.

## Provider and platform adapters

- GitHub Actions composes the public actions or small reusable job workflows.
- Another CI provider runs the documented `nix run` command and publishes `.bertie-ci`
  logs; it does not reimplement the test.
- Linux uses the pinned Nix closure, Xvfb, and Mesa software rendering.
- Windows runs the same Python package, selects `gradlew.bat`, and uses the native
  display. Exact HeadlessHQ JAR paths and Java are injectable through environment
  variables until a Windows package is published.

## Stabilization gates

Before broad rollout:

- the shared flake check is green on GitHub;
- the `bertie-tiers` local and hosted client/server probes are green;
- failures point at retained logs and crash reports;
- the public actions and job workflows are tagged `v3.3.3`, and callers use that
  immutable release rather than bootstrap `@main`;
- dependency fixtures are hash-pinned and side-aware;
- a full-pack run has a measured cold-cache and warm-cache duration.

The shared-action gates are complete. `v3.3.1` added the full desktop JDK needed when a
client mod initializes AWT and made repeated probes safe when Nix-sourced JARs are
read-only. `v3.3.2` provisions the accepted Minecraft EULA directly so a large dedicated
server does not perform a redundant preliminary launch. `v3.3.3` gives HeadlessMC's
internal readiness test the caller's timeout and keeps a successful readiness assertion
independent of a slow post-`stop` exit. Prepared full-pack probes completed locally on
aarch64 in about four minutes for a 460-mod client world join and 3m37s for
dedicated-server readiness after dependencies were assembled; hosted rollout remains the
next phase. The earlier title-menu experiment is not the baseline because a UI
onboarding
screen blocked it without proving whether an integrated world could load. The first
prepared full-pack world-join run already improved on that signal: it reached the first
client tick and exposed Immersive Armors attempting a late armor-material registration, a
product failure that a title-menu assertion would have missed.
