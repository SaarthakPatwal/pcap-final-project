param([switch]$Build)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# Prefer the installed 64-bit toolchain over the older 32-bit C:\MinGW.
$thermalToolchain = 'C:\Program Files\CodeBlocks\MinGW\bin'
if (Test-Path -LiteralPath $thermalToolchain) {
    $env:PATH = $thermalToolchain + ';' + $env:PATH
}
if (-not $env:OMP_NUM_THREADS) { $env:OMP_NUM_THREADS = '8' }
if ($Build) {
    cmake -S . -B build -G 'MinGW Makefiles' -DENABLE_CUDA=OFF -DCMAKE_BUILD_TYPE=Release
    if ($LASTEXITCODE -ne 0) { throw 'CMake configuration failed.' }
    cmake --build build -j 4
    if ($LASTEXITCODE -ne 0) { throw 'Native build failed.' }
}
$thermalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $thermalPython)) {
    throw 'Create .venv and install requirements.txt first. See README.md.'
}
& $thermalPython server\app.py
