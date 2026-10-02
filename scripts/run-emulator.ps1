<#
.SYNOPSIS
    Boots the built Ikemen Saturn disc in the LibSaturn Ymir probe.

.DESCRIPTION
    The probe is a separate tool (LibSaturn's harness/, GPL-3.0); this project
    does not build or vendor it. Point -Probe (or $env:IKEMEN_PROBE) at a
    probe.exe. A Saturn BIOS dump is required too (-Bios or $env:LIBSATURN_BIOS);
    it is Sega's property and is not provided here.

    Ikemen Saturn needs the 4 MiB RAM cartridge, which the script plugs in.

.EXAMPLE
    scripts/run-emulator.ps1 -Frames 600 -PadScript scripts/pads/ikemen_moves.pad `
        -Screenshot 590:build/shots/fight.png
#>
[CmdletBinding()]
param(
    [string]$Probe,
    [string]$Bios,
    [string]$BuildDir,
    [int]$Frames = 600,
    [int]$BootFrames = 90,
    [string]$PadScript,
    [string[]]$Screenshot,
    [string]$Out,
    [switch]$Pal
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $PSScriptRoot
if (-not $Probe) { $Probe = $env:IKEMEN_PROBE }
if (-not $Probe -or -not (Test-Path $Probe)) {
    throw 'No probe: pass -Probe <probe.exe> or set IKEMEN_PROBE (LibSaturn harness probe).'
}
if (-not $Bios) { $Bios = $env:LIBSATURN_BIOS }
if (-not $Bios -or -not (Test-Path $Bios)) {
    throw 'No BIOS: pass -Bios <saturn_bios.bin> or set LIBSATURN_BIOS (your own dump).'
}
if (-not $BuildDir) { $BuildDir = Join-Path $Root 'build\saturn' }
$iso = Join-Path $BuildDir 'disc\ikemen_saturn.iso'
$bin = Join-Path $BuildDir 'ikemen_saturn.app.bin'
foreach ($f in @($iso, $bin)) {
    if (-not (Test-Path $f)) { throw "Missing $f. Build first: cmake --preset saturn; cmake --build --preset saturn" }
}
if (-not $Out) { $Out = Join-Path $BuildDir 'probe.json' }

$probeArgs = @('--iso', $iso, '--bios', $Bios, '--bin', $bin,
    '--frames', $Frames, '--boot-frames', $BootFrames,
    '--ram-cart', '4m', '--out', $Out)
if ($PadScript) { $probeArgs += @('--pad-script', $PadScript) }
foreach ($shot in $Screenshot) {
    $path = ($shot -split ':', 2)[1]
    $dir = Split-Path -Parent $path
    if ($dir) { New-Item -ItemType Directory -Force $dir | Out-Null }
    $probeArgs += @('--screenshot', $shot)
}
if ($Pal) { $probeArgs += '--pal' }

Write-Host "[run-emulator] $Probe $($probeArgs -join ' ')"
# The emulator core logs thousands of debug lines; keep the probe's own report.
$log = [System.IO.Path]::ChangeExtension($Out, '.log')
& $Probe @probeArgs 2>&1 | Tee-Object -FilePath $log | Where-Object { $_ -match '^(\[probe\]|probe:|error|warn)' } | Out-Host
$global:LASTEXITCODE = $LASTEXITCODE
if ($global:LASTEXITCODE -ne 0) { throw "probe failed (exit $global:LASTEXITCODE)" }
Write-Host "[run-emulator] done: $Out (full emulator log: $log)"
