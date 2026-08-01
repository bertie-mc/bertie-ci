{
  description = "Local-first Minecraft runtime checks for bertie-mc";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

    flake-parts = {
      url = "github:hercules-ci/flake-parts";
      inputs.nixpkgs-lib.follows = "nixpkgs";
    };

    treefmt-nix = {
      url = "github:numtide/treefmt-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    bertie-pack = {
      url = "github:bertie-mc/bertie-pack";
      flake = false;
    };
  };

  outputs =
    inputs@{
      self,
      flake-parts,
      ...
    }:
    flake-parts.lib.mkFlake { inherit inputs; } {
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];

      imports = [ inputs.treefmt-nix.flakeModule ];

      perSystem =
        { config, pkgs, ... }:
        let
          package = pkgs.callPackage ./nix/package.nix {
            bertie-pack = inputs.bertie-pack.outPath;
          };
          app = {
            program = package;
            meta.description = package.meta.description;
          };
        in
        {
          packages = {
            default = package;
            bertie-ci = package;
          };

          apps = {
            default = app;
            bertie-ci = app;
          };

          checks = {
            inherit package;
            help =
              pkgs.runCommand "bertie-ci-help"
                {
                  nativeBuildInputs = [ package ];
                }
                ''
                  bertie-ci --help > "$out"
                '';
            workflows =
              pkgs.runCommand "bertie-ci-workflows"
                {
                  source = self.outPath;
                  nativeBuildInputs = [
                    pkgs.action-validator
                    pkgs.actionlint
                  ];
                }
                ''
                  cd "$source"
                  actionlint .github/workflows/*.yml
                  action-validator actions/*/action.yml .github/workflows/*.yml
                  touch "$out"
                '';
          };

          devShells.default = pkgs.mkShellNoCC {
            packages = [
              config.treefmt.build.wrapper
              pkgs.action-validator
              pkgs.actionlint
              pkgs.gradle_8
              pkgs.jdk21
              pkgs.python3
              pkgs.python3Packages.pytest
              pkgs.ruff
            ];
          };

          treefmt.programs = {
            nixfmt.enable = true;
            ruff-check = {
              enable = true;
              extendSelect = [ "I" ];
            };
            ruff-format.enable = true;
          };
        };
    };
}
