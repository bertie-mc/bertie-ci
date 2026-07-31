# Runtime fixture profiles

`profiles.json` maps a profile name to the basenames of mod metafiles in the canonical
[`bertie-pack`](https://github.com/bertie-mc/bertie-pack) checkout. `defaults.json`
defines the same kind of list for every client or server probe.

The metafiles themselves do not live here. The Nix flake pins an immutable
`bertie-pack` revision and the runner verifies that revision's `pack.toml`, `index.toml`,
Minecraft/NeoForge versions, entry hashes, and metafile flags before generating a small
temporary pack. This keeps the shipping pack as the single source of truth for mod
versions, filenames, sides, and downloads.

Packwiz metafiles do not record dependency closure. When adding a profile, list the
target mod and every required top-level dependency from the canonical pack, then prove
the profile with the smallest relevant client and/or server pilot.

Update the canonical snapshot deliberately:

```bash
nix flake update bertie-pack
nix flake check
```

Review the `flake.lock` revision and the affected generated fixture before publishing a
new `bertie-ci` tag.
