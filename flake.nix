{
  description = "Local-first Minecraft runtime checks for bertie-mc";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs, ... }:
    let
      versions = builtins.fromJSON (builtins.readFile ./versions.json);
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
          headlessmc = pkgs.fetchurl {
            inherit (versions.headlessmc) url hash;
          };
          mcRuntimeTest = pkgs.fetchurl {
            inherit (versions.mc_runtime_test) url hash;
          };
          packwizInstaller = pkgs.fetchurl {
            inherit (versions.packwiz_installer) url hash;
          };
          bertie-ci = pkgs.python3Packages.buildPythonApplication {
            pname = "bertie-ci";
            version = "0.1.0";
            pyproject = true;
            src = ./.;
            build-system = [ pkgs.python3Packages.setuptools ];
            nativeBuildInputs = [ pkgs.makeWrapper ];
            nativeCheckInputs = [ pkgs.python3Packages.pytestCheckHook ];
            postFixup = ''
              wrapProgram "$out/bin/bertie-ci" \
                --prefix PATH : ${
                  pkgs.lib.makeBinPath [
                    pkgs.bash
                    pkgs.coreutils
                    pkgs.jdk21_headless
                    pkgs.mesa-demos
                    pkgs.xorg-server
                  ]
                } \
                --set-default BERTIE_CI_SHELL ${pkgs.bash}/bin/sh \
                --set-default BERTIE_CI_VERSIONS ${./versions.json} \
                --set-default BERTIE_CI_HEADLESSMC_JAR ${headlessmc} \
                --set-default BERTIE_CI_MCRT_JAR ${mcRuntimeTest} \
                --set-default BERTIE_CI_PACKWIZ_INSTALLER_JAR ${packwizInstaller} \
                --set-default BERTIE_CI_FIXTURES ${./fixtures} \
                --set-default BERTIE_CI_JAVA_HOME ${pkgs.jdk21_headless} \
                --set-default BERTIE_CI_XVFB ${pkgs.xorg-server}/bin/Xvfb \
                --set-default BERTIE_CI_GLXINFO ${pkgs.mesa-demos}/bin/glxinfo \
                --set LIBGL_DRIVERS_PATH ${pkgs.mesa}/lib/dri \
                --set XORG_MODULE_PATH ${pkgs.xorg-server}/lib/xorg/modules \
                --prefix LD_LIBRARY_PATH : ${
                  pkgs.lib.makeLibraryPath [
                    pkgs.alsa-lib
                    pkgs.libglvnd
                    pkgs.libpulseaudio
                    pkgs.flite
                    pkgs.libX11
                    pkgs.libXcursor
                    pkgs.libXext
                    pkgs.libXfixes
                    pkgs.libXi
                    pkgs.libXinerama
                    pkgs.libXrandr
                    pkgs.libXrender
                    pkgs.libXxf86vm
                    pkgs.libxcb
                    pkgs.mesa
                    pkgs.openal
                  ]
                }
            '';
            pythonImportsCheck = [ "bertie_ci" ];
          };
        in
        {
          default = bertie-ci;
          inherit bertie-ci;
        }
      );

      apps = forAllSystems (
        system:
        let
          app = {
            type = "app";
            program = "${self.packages.${system}.bertie-ci}/bin/bertie-ci";
          };
        in
        {
          default = app;
          bertie-ci = app;
        }
      );

      checks = forAllSystems (
        system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          package = self.packages.${system}.bertie-ci;
          help = pkgs.runCommand "bertie-ci-help" { } ''
            ${self.packages.${system}.bertie-ci}/bin/bertie-ci --help > "$out"
          '';
        }
      );
    };
}
