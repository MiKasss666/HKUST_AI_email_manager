# Build an installable .difypkg for Dify.
#
#   powershell -ExecutionPolicy Bypass -File scripts/package_plugin.ps1
#
# Prefer the official Dify plugin CLI when available (`dify plugin package
# ./plugin/email_manager`); it validates the package as well. This script is a
# dependency-free fallback that produces the same kind of zip.

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
py -3 (Join-Path $PSScriptRoot 'package_plugin.py')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
