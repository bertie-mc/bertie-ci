{
  lib,
  python3Packages,
  fetchurl,
  bash,
  coreutils,
  jdk21,
  mesa-demos,
  packwiz,
  xorg-server,
  alsa-lib,
  libglvnd,
  libpulseaudio,
  flite,
  libX11,
  libXcursor,
  libXext,
  libXfixes,
  libXi,
  libXinerama,
  libXrandr,
  libXrender,
  libXxf86vm,
  libxcb,
  mesa,
  openal,
  bertiePack,
}:
let
  pyproject = lib.importTOML ../pyproject.toml;
  versions = lib.importJSON ../versions.json;

  headlessmc = fetchurl {
    inherit (versions.headlessmc) url hash;
  };
  mcRuntimeTest = fetchurl {
    inherit (versions.mc_runtime_test) url hash;
  };
  packwizInstaller = fetchurl {
    inherit (versions.packwiz_installer) url hash;
  };

  runtimePath = lib.makeBinPath [
    bash
    coreutils
    jdk21
    mesa-demos
    packwiz
    xorg-server
  ];
  runtimeLibraryPath = lib.makeLibraryPath [
    alsa-lib
    libglvnd
    libpulseaudio
    flite
    libX11
    libXcursor
    libXext
    libXfixes
    libXi
    libXinerama
    libXrandr
    libXrender
    libXxf86vm
    libxcb
    mesa
    openal
  ];
in
python3Packages.buildPythonApplication {
  pname = pyproject.project.name;
  inherit (pyproject.project) version;
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../UNLICENSE
      ../fixtures
      ../pyproject.toml
      ../src
      ../tests
    ];
  };

  build-system = [ python3Packages.setuptools ];

  nativeCheckInputs = [ python3Packages.pytestCheckHook ];
  preCheck = ''
    export BERTIE_CI_FIXTURE_PACK=${bertiePack}
  '';

  __structuredAttrs = true;
  makeWrapperArgs = [
    "--prefix"
    "PATH"
    ":"
    runtimePath
    "--set-default"
    "BERTIE_CI_SHELL"
    (lib.getExe' bash "sh")
    "--set-default"
    "BERTIE_CI_VERSIONS"
    ../versions.json
    "--set-default"
    "BERTIE_CI_HEADLESSMC_JAR"
    headlessmc
    "--set-default"
    "BERTIE_CI_MCRT_JAR"
    mcRuntimeTest
    "--set-default"
    "BERTIE_CI_PACKWIZ_INSTALLER_JAR"
    packwizInstaller
    "--set-default"
    "BERTIE_CI_PACKWIZ"
    (lib.getExe packwiz)
    "--set-default"
    "BERTIE_CI_FIXTURES"
    ../fixtures
    "--set-default"
    "BERTIE_CI_FIXTURE_PACK"
    bertiePack
    "--set-default"
    "BERTIE_CI_JAVA_HOME"
    jdk21
    "--set-default"
    "BERTIE_CI_XVFB"
    (lib.getExe' xorg-server "Xvfb")
    "--set-default"
    "BERTIE_CI_GLXINFO"
    (lib.getExe' mesa-demos "glxinfo")
    "--set"
    "LIBGL_DRIVERS_PATH"
    "${mesa}/lib/dri"
    "--set"
    "XORG_MODULE_PATH"
    "${xorg-server}/lib/xorg/modules"
    "--prefix"
    "LD_LIBRARY_PATH"
    ":"
    runtimeLibraryPath
  ];

  pythonImportsCheck = [ "bertie_ci" ];

  meta = {
    description = pyproject.project.description;
    homepage = "https://github.com/bertie-mc/bertie-ci";
    license = lib.licenses.unlicense;
    mainProgram = "bertie-ci";
    platforms = lib.platforms.linux;
  };
}
