#!/usr/bin/env pwsh
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host "1. Running Python unit & security tests..." -ForegroundColor Cyan
python -m unittest discover -s tests -v
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "2. Checking JavaScript, Python CLI, and POSIX shell syntax..." -ForegroundColor Cyan
foreach ($js in @("assets/app.js", "assets/preview.js", "assets/reconnect.js")) {
    node --check $js
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
python -m py_compile scripts/porkbun-dns.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$gitSh = "C:\Program Files\Git\bin\sh.exe"
$posixSh = if (Test-Path $gitSh) { $gitSh } else { (Get-Command sh -ErrorAction SilentlyContinue | Select-Object -First 1).Source }
if ($posixSh) {
    foreach ($shFile in (Get-Item scripts/*.sh, startup/*.sh)) {
        & $posixSh -n $shFile.FullName
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
}

Write-Host "3. Checking C++17 firmware simulation..." -ForegroundColor Cyan
$cxx = Get-Command g++, clang++, c++ -ErrorAction SilentlyContinue | Select-Object -First 1
if ($cxx) {
    $tmpExe = Join-Path ([System.IO.Path]::GetTempPath()) "hush-firmware-test.exe"
    try {
        & $cxx.Source -std=c++17 -I tests/firmware_stub tests/test_firmware.cpp -o $tmpExe
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        & $tmpExe
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    } finally {
        Remove-Item $tmpExe -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Warning "No host C++ compiler found on Windows PATH; skipping firmware binary check."
}

Write-Host "All Hush verification checks passed!" -ForegroundColor Green
