# Running bertie-ci on Windows

Nix is the supported dependency provider on Linux, and there is no usable Nix on native
Windows. The commands themselves are ordinary Python and do not assume a POSIX shell, so
Windows supplies the same dependencies through environment variables instead. This
document is the Windows equivalent of the `nix run` lines in the README.

Everything here is native Windows. WSL is not required, and if you do use WSL you are on
the Linux path and should follow the README instead.

## What runs

| Command | Windows | Extra requirements |
| --- | --- | --- |
| `build` | Yes | Gradle 8 and Java 21 |
| `unit-test` | Yes | Gradle 8 and Java 21 |
| `gametest` | Yes | Gradle 8 and Java 21 |
| `server` | Yes | Java 21 and the three tool JARs |
| `client` | Yes, but not headless | Java 21, the three tool JARs, and an interactive desktop session |

`build`, `unit-test` and `gametest` invoke the Gradle executable selected by
`BERTIE_CI_GRADLE`, falling back to `gradle` on `PATH`. Projects do not carry wrappers.

`client` is the one command that behaves differently. Windows has no Xvfb equivalent, so
the probe runs against the desktop session you are logged into: a real Minecraft window
opens, takes focus, and closes itself when the probe finishes. It cannot run over SSH, as
a service, or on a locked workstation. Treat `client` on Windows as a foreground task that
occupies the machine for its duration; Linux with Xvfb remains the way to run it
unattended.

## Prerequisites

Gradle 8.14.4, Java 21, and Python 3.11 or newer on `PATH`, plus `JAVA_HOME` pointing at
the JDK root. The runner reads `BERTIE_CI_JAVA_HOME` first and falls back to `JAVA_HOME`.

```powershell
gradle --version; java -version; python --version; $env:JAVA_HOME
```

If `JAVA_HOME` is unset, set it for the current session and persist it separately:

```powershell
$env:JAVA_HOME = "C:\Program Files\Eclipse Adoptium\jdk-21.0.11.10-hotspot"
[Environment]::SetEnvironmentVariable("JAVA_HOME", $env:JAVA_HOME, "User")
```

Enable long paths. Minecraft's runtime directories nest deeply below the project, and the
legacy 260-character limit is reached in ordinary use. This needs an elevated shell and a
reboot:

```powershell
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -Value 1
```

Confirm it took effect with:

```powershell
(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem').LongPathsEnabled
```

## Getting the CLI

There is no published wheel. Clone the repository and run the package from the checkout,
which also keeps `versions.json` and `fixtures/` on the paths the runner expects:

```powershell
git clone https://github.com/bertie-mc/bertie-ci.git
git clone https://github.com/bertie-mc/bertie-pack.git
cd bertie-ci
$packRev = (Get-Content .\flake.lock | ConvertFrom-Json).nodes.'bertie-pack'.locked.rev
git -C ..\bertie-pack checkout $packRev
$env:BERTIE_CI_FIXTURE_PACK = (Resolve-Path ..\bertie-pack)
$env:PYTHONPATH = "$PWD\src"
python -m bertie_ci --help
```

`uv` works too and gives you the `bertie-ci` console script:

```powershell
uv run bertie-ci --help
```

An installed copy does not carry `versions.json` or the fixture catalog, because both
sit outside the Python package. Point `BERTIE_CI_VERSIONS` and `BERTIE_CI_FIXTURES` at the
checkout if you install the package somewhere else. Runtime fixture commands also need
`BERTIE_CI_FIXTURE_PACK` to identify the canonical pack checkout. The commands above use
the exact revision pinned by `flake.lock`, matching Linux and hosted CI.

## Build, unit tests, and GameTests

These need no further setup. Point `--project` at a mod checkout:

```powershell
python -m bertie_ci build --project C:\src\bertie-tiers --output-dir .bertie-ci\artifact
```

```powershell
python -m bertie_ci unit-test --project C:\src\bertie-tiers
```

```powershell
python -m bertie_ci gametest --project C:\src\bertie-tiers
```

A relative `--output-dir` resolves against `--project`, not the current directory, so the
command above writes to `C:\src\bertie-tiers\.bertie-ci\artifact`. GameTest logs land in
`<project>\.bertie-ci\gametest.log`.

## Tool JARs for the runtime probes

`client` and `server` need the three pinned third-party JARs that the Nix flake supplies
on Linux. Both commands validate all three up front, so `server` wants the
`mc-runtime-test` JAR present even though only `client` launches it. Download them once
and point the environment at them. The versions and hashes below are the ones in
[`versions.json`](../versions.json); if that file has moved on, it is authoritative and
this table is not.

| Environment variable | File | Size |
| --- | --- | --- |
| `BERTIE_CI_HEADLESSMC_JAR` | `headlessmc-launcher-2.10.0.jar` | 12.4 MB |
| `BERTIE_CI_MCRT_JAR` | `mc-runtime-test-1.21.1-4.5.1-neoforge-release.jar` | 320 KB |
| `BERTIE_CI_PACKWIZ_INSTALLER_JAR` | `packwiz-installer.jar` | 4.2 MB |

This downloads all three into `%LOCALAPPDATA%\bertie-ci\tools` and fails if any hash does
not match the pin:

```powershell
$tools = "$env:LOCALAPPDATA\bertie-ci\tools"
New-Item -ItemType Directory -Force $tools | Out-Null

$pinned = @(
  @{ Name = "headlessmc-launcher-2.10.0.jar"
     Url  = "https://github.com/headlesshq/headlessmc/releases/download/2.10.0/headlessmc-launcher-2.10.0.jar"
     Hash = "52bd5006f478377b3893011d458562977d38c65ead6d2b31089beb4d614f13cd" }
  @{ Name = "mc-runtime-test-1.21.1-4.5.1-neoforge-release.jar"
     Url  = "https://github.com/headlesshq/mc-runtime-test/releases/download/4.5.1/mc-runtime-test-1.21.1-4.5.1-neoforge-release.jar"
     Hash = "404e566645730470dc873db88c28d483995c9b7bb6999a6a2af9630a41bf7774" }
  @{ Name = "packwiz-installer.jar"
     Url  = "https://github.com/packwiz/packwiz-installer/releases/download/v0.5.14/packwiz-installer.jar"
     Hash = "c9f646908d340d84773948a9a7d98bc1dae250d35e1016dc6e2b8459760b5598" }
)

foreach ($jar in $pinned) {
  $path = Join-Path $tools $jar.Name
  if (-not (Test-Path $path)) { Invoke-WebRequest -Uri $jar.Url -OutFile $path }
  $actual = (Get-FileHash $path -Algorithm SHA256).Hash.ToLower()
  if ($actual -ne $jar.Hash) { throw "$($jar.Name): expected $($jar.Hash), got $actual" }
  "$($jar.Name) OK"
}
```

Then declare them for the session:

```powershell
$env:BERTIE_CI_HEADLESSMC_JAR = "$tools\headlessmc-launcher-2.10.0.jar"
$env:BERTIE_CI_MCRT_JAR = "$tools\mc-runtime-test-1.21.1-4.5.1-neoforge-release.jar"
$env:BERTIE_CI_PACKWIZ_INSTALLER_JAR = "$tools\packwiz-installer.jar"
```

## Running the runtime probes

Build first, then hand the artifact to each probe:

```powershell
python -m bertie_ci build --project C:\src\bertie-tiers --output-dir .bertie-ci\artifact
python -m bertie_ci server --project C:\src\bertie-tiers --artifact .bertie-ci\artifact
python -m bertie_ci client --project C:\src\bertie-tiers --artifact .bertie-ci\artifact
```

Mods with external runtime dependencies select canonical mods or aggregate fixture
profiles exactly as on Linux:

```powershell
python -m bertie_ci client --project C:\src\forge-ink --fixture forbidden-arcanus,irons-spells
```

The first run downloads Minecraft and the pinned NeoForge build. Both land in the cache,
not the project, and are reused by later runs.

## Environment variables

| Variable | Purpose | Windows default |
| --- | --- | --- |
| `BERTIE_CI_JAVA_HOME` | JDK root; takes precedence over `JAVA_HOME` | unset |
| `BERTIE_CI_GRADLE` | Gradle executable | `gradle` from `PATH` |
| `BERTIE_CI_HEADLESSMC_JAR` | HeadlessMC launcher JAR | required for `client`/`server` |
| `BERTIE_CI_MCRT_JAR` | `mc-runtime-test` probe JAR | required for `client`/`server` |
| `BERTIE_CI_PACKWIZ_INSTALLER_JAR` | packwiz-installer JAR | required for `client`/`server` |
| `BERTIE_CI_VERSIONS` | Path to `versions.json` | repository root |
| `BERTIE_CI_FIXTURES` | Path to fixture aggregates and defaults | `fixtures/` in the repository |
| `BERTIE_CI_FIXTURE_PACK` | Canonical `bertie-pack` checkout | required when installing fixtures |
| `BERTIE_CI_XVFB` | Xvfb binary | unset, and unusable on Windows |
| `BERTIE_CI_GLXINFO` | `glxinfo` binary for the GL preflight | unset, and unusable on Windows |
| `XDG_CACHE_HOME` | Parent of the Minecraft cache | `%USERPROFILE%\.cache` |

The cache path is deliberately the same on every platform, so it is `C:\Users\<you>\.cache\bertie-ci`
rather than somewhere under `%LOCALAPPDATA%`. Pass `--cache-dir` to put it elsewhere.

## Troubleshooting

**`Java not found at ...`** — `JAVA_HOME` is pointing at a JRE, at a directory one level
too deep, or at a path that no longer exists. The runner expects `<JAVA_HOME>\bin\java.exe`.

**`gradle` is not recognized** — install Gradle 8.14.4 and add it to `PATH`, or point
`BERTIE_CI_GRADLE` at the executable. Gradle 9 is not supported by the current
ModDevGradle setup.

**A build or probe fails with a path that stops mid-way through, or a `Malformed \uxxxx
encoding` error** — this was a real defect and is fixed. Windows paths were written into
HeadlessMC's `config.properties` without escaping, and `java.util.Properties` treats a
backslash as an escape character, so `C:\Users\berlord` was read back as `C:Usersberlord`
and any lowercase `\u` segment threw outright. If you see this, you are on a build from
before that fix.

**`PermissionError` while clearing `.bertie-ci\client\run`** — a previous run left a
read-only or still-locked file. Read-only files are handled; a locked one is not, and
means a Java process from an earlier run is still alive or a virus scanner is holding the
directory open. Close it and retry.

**Antivirus makes runs very slow** — real-time scanning inspects every file Minecraft
extracts. Excluding the cache directory and the project's `.bertie-ci` directory is the
usual remedy.

**The client probe fails on a remote or locked session** — expected. See *What runs*
above; `client` needs an interactive desktop.
