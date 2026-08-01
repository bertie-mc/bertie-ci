# Runtime fixtures

Fixture selectors resolve directly to mod metafile basenames in the canonical
[`bertie-pack`](https://github.com/bertie-mc/bertie-pack) checkout. For example,
`--fixture create` selects `mods/create.pw.toml` without an entry in this repository.

`profiles.json` is only for aggregate dependency closures: a selector such as `artifacts`
maps to both `artifacts` and `curios`. Each profile must contain at least two mods;
one-to-one aliases belong in neither the catalog nor the Python code. `defaults.json`
lists canonical mods installed for every client or server fixture instance.

The metafiles themselves do not live here. The Nix flake pins an immutable
`bertie-pack` revision and the runner verifies that revision's `pack.toml`, `index.toml`,
Minecraft/NeoForge versions, entry hashes, and metafile flags before generating a small
temporary pack. This keeps the shipping pack as the single source of truth for mod
versions, filenames, sides, and downloads.

Packwiz metafiles do not record dependency closure. Add a profile only when a mod needs
other top-level canonical mods to load. List the target and every required dependency,
then prove the aggregate with the smallest relevant client and/or server pilot.

Update the canonical snapshot deliberately:

```bash
nix flake update bertie-pack
nix flake check
```

Review the `flake.lock` revision and the affected generated fixture before publishing a
new `bertie-ci` tag.
