param([switch]$Native)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'Run uv sync --frozen first.' }
Push-Location $projectRoot
try {
    & $pythonExe tools/check_project.py
    if ($LASTEXITCODE -ne 0) { throw 'Documentation checks failed.' }
    & $pythonExe -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Python tests failed.' }
    if ($Native) {
        cmake -S firmware -B build/firmware-native -G 'Visual Studio 16 2019' -A x64
        if ($LASTEXITCODE -ne 0) { throw 'Native configuration failed.' }
        cmake --build build/firmware-native --config Release
        if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }
        $ctestExe = Join-Path (Split-Path (Get-Command cmake).Source) 'ctest.exe'
        & $ctestExe --test-dir build/firmware-native -C Release --output-on-failure
        if ($LASTEXITCODE -ne 0) { throw 'Native tests failed.' }
    }
    git diff --check
    if ($LASTEXITCODE -ne 0) { throw 'Whitespace check failed.' }
} finally {
    Pop-Location
}
