<#
  Asset Vault installer for Windows - PowerShell only, no bash, no git.

      .\install.ps1                        newest Blender found on this machine
      .\install.ps1 -BlenderAddons "C:\Users\you\AppData\Roaming\Blender Foundation\Blender\5.2\scripts\addons"

  If Windows refuses to run the script, start it like this instead:

      powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1

  This is install.sh's other door: the add-on's own folder is copied into Blender's
  user "scripts/addons", which is where Edit > Preferences > Add-ons looks.  Nothing
  outside that folder is touched, and the env var the shell installer honours
  (BLENDER_ADDON_DIR, plus BLENDER_CONFIG_DIR for the config root) works here too.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string] $BlenderAddons
)

$ErrorActionPreference = 'Stop'
$Repo = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-BlenderAddons {
    if ($BlenderAddons) { return $BlenderAddons }
    if ($env:BLENDER_ADDON_DIR) { return $env:BLENDER_ADDON_DIR }
    $root = if ($env:BLENDER_CONFIG_DIR) { $env:BLENDER_CONFIG_DIR }
            else { Join-Path $env:APPDATA 'Blender Foundation\Blender' }
    # The leaf names are all 'addons'; compare the version directory instead.
    $versions = @(Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match '^\d+\.\d+(\.\d+)?$' -and
            (Test-Path -LiteralPath (Join-Path $_.FullName 'scripts\addons') -PathType Container)
        } |
        Sort-Object -Property @{Expression = { [version]$_.Name }} -Descending)
    if ($versions.Count -gt 0) {
        return Join-Path $versions[0].FullName 'scripts\addons'
    }
    return $null
}

$addons = Get-BlenderAddons
if (-not $addons) {
    Write-Host "no Blender 'scripts/addons' folder found - pass one:" -ForegroundColor Red
    Write-Host '  .\install.ps1 "<...>\scripts\addons"'
    exit 2
}
if (-not (Test-Path -LiteralPath $addons -PathType Container)) {
    Write-Host "not a folder: $addons" -ForegroundColor Red
    exit 2
}

$source = Join-Path $Repo 'asset_vault'
if (-not (Test-Path -LiteralPath (Join-Path $source '__init__.py') -PathType Leaf)) {
    Write-Host "missing $source\__init__.py - unzip the whole release, not just this file" -ForegroundColor Red
    exit 1
}

$target = Join-Path $addons 'asset_vault'
if (Test-Path -LiteralPath $target) { Remove-Item -Recurse -Force $target }
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source '*') -Destination $target -Recurse -Force
Get-ChildItem -Path $target -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "installed asset_vault -> $target"
Write-Host 'now enable it: Edit > Preferences > Add-ons > search "Asset Vault"'
