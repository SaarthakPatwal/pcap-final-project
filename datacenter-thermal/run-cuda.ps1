$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$thermalLibrary = Join-Path $PSScriptRoot 'build-cuda-vs\Release\thermal.dll'
$thermalPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$openMpRuntime = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Redist\MSVC\14.44.35112\debug_nonredist\x64\Microsoft.VC143.OpenMP.LLVM'

if (-not (Test-Path -LiteralPath $thermalLibrary)) {
    throw 'CUDA library is missing. Run .\build-cuda.cmd first.'
}
if (-not (Test-Path -LiteralPath $thermalPython)) {
    throw 'Python virtual environment is missing. See README.md.'
}

$env:THERMAL_LIBRARY = $thermalLibrary
$env:OMP_NUM_THREADS = '8'
$env:PATH = $openMpRuntime + ';' + $env:PATH
& $thermalPython server\app.py
