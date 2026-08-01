# AGENTS.md

Instructions for agents working on the shared `bertie-mc` test infrastructure.

## Source of truth

GitHub is the source of truth. Before finishing:

```bash
git add -A
git commit -m "type(scope): what changed"
git pull --rebase origin main
git push origin main
```

Leave a clean working tree and exactly one worktree. Use Conventional Commits and never
force-push.

## Architecture

- The command-line tools are the product. They must run locally through Nix without a CI
  provider.
- Reusable GitHub workflows are thin adapters around those commands. Do not put test
  logic in workflow YAML.
- Minecraft, NeoForge, Java, HeadlessMC, and runtime-test versions are exact pins. Do not float
  loader builds or silently update the shared toolchain.
- Third-party binaries must be fixed-output Nix inputs with verified hashes.
- Runtime instances and downloaded JARs are ephemeral. Never commit JARs or generated
  Minecraft directories.
- Keep instance assembly separate from runtime assertions. Both mod fixtures and full
  packs must feed the same client/server runners.

## Verification

Run at least:

```bash
nix flake check
nix run .#bertie-ci -- --help
```

For runtime changes, also run the smallest relevant local mod pilot and preserve its logs.
