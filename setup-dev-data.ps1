# Setup script for local development test data
# Runs in PowerShell; creates sample directory structure

param(
    [string]$BaseDir = "$env:LOCALAPPDATA\jellyfin-refresh-test"
)

Write-Host "Creating test data structure in: $BaseDir"

# Create directory structure
$dirs = @(
    "$BaseDir\debrid_4k\shows",
    "$BaseDir\debrid_4k\movies",
    "$BaseDir\debrid_1080\shows",
    "$BaseDir\debrid_1080\movies",
    "$BaseDir\media\shows",
    "$BaseDir\media\movies",
    "$BaseDir\scripts"
)

foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Created: $dir"
    }
}

# Create sample show directories
$shows = @("Breaking Bad", "The Office", "Game of Thrones", "Stranger Things", "The Crown")
foreach ($show in $shows) {
    $path = "$BaseDir\media\shows\$show"
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "Created show: $show"
    }
}

# Create sample movie directories
$movies = @("Inception", "Interstellar", "The Matrix", "Gladiator", "Oppenheimer")
foreach ($movie in $movies) {
    $path = "$BaseDir\media\movies\$movie"
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
        Write-Host "Created movie: $movie"
    }
}

# Create a mock sync script (batch file that echoes output)
$mockScriptBat = @"
@echo off
REM Mock sync script for local testing
echo Mock sync started for: %*
timeout /t 2 /nobreak
echo Mock sync complete!
exit /b 0
"@

$scriptPath = "$BaseDir\scripts\mock_sync.bat"
Set-Content -Path $scriptPath -Value $mockScriptBat -Force
Write-Host "Created mock script: $scriptPath"

Write-Host "`nSetup complete! Test data ready in: $BaseDir"
Write-Host "`nTo use local dev mode, set the DEV_MODE environment variable:"
Write-Host "  `$env:DEV_MODE = 'true'"
Write-Host "`nThen run the app:"
Write-Host "  python app.py"
