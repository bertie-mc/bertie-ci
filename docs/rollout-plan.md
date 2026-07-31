# Headless runtime-test rollout

## Decisions

`bertie-ci` is the test product. Its build, GameTest, client, and server commands are
independent operations. Small composite actions map one-to-one to those commands. Small
reusable job workflows add only checkout or artifact transport; repository workflows
retain their dependency graph. The runtime code stays in Python so process
management, timeouts, paths, and Windows-specific Gradle launching are not encoded in
shell scripts.

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
therefore remain a third, separate layer run by Gradle's development runtime. A runtime
world join and a GameTest run cover different failure modes and neither replaces the
other.

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
5. Keep compilation and unit tests in `build`, run Gradle GameTests as a separate
   development-runtime job, and feed the built JAR artifact to separate production
   probes. No test command silently rebuilds the artifact it was asked to verify.

All 20 custom NeoForge mods compose the shared `v3.0.1` build and runtime jobs. Three
physically client-only projects omit the server job; common projects compose both.
Dependency-bearing mods use the declarative `fdlib`, `forbidden-arcanus`, `ftb-filters`,
`irons-spells`, `rustic-engineer`, and `simply-swords` profiles. Only the two projects
that currently contain registered GameTests compose the separate GameTest job. Release
workflows compose the same build job with an artifact-only GitHub publisher.

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
- the public actions and job workflows are tagged `v3.0.1`, and callers use that
  immutable release rather than bootstrap `@main`;
- dependency fixtures are hash-pinned and side-aware;
- a full-pack run has a measured cold-cache and warm-cache duration.

The first five gates are complete. Full-pack timing and rollout remain the next phase;
the earlier title-menu experiment is not the baseline because a UI onboarding screen
blocked it without proving whether an integrated world could load.
