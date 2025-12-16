# Setup script for local development test data
# Runs in PowerShell; creates sample directory structure with mock media files

param(
    [string]$BaseDir = "$env:LOCALAPPDATA\jellyfin-refresh-test"
)

Write-Host "Creating test data structure in: $BaseDir"

# -----------------------------
# Directory structure
# -----------------------------
$dirs = @(
    "$BaseDir\debrid\shows",
    "$BaseDir\debrid\movies",
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

# -----------------------------
# Show data (seasons & episodes)
# -----------------------------
$shows = @(
    @{ Name = "Breaking Bad"; Seasons = 2; EpisodesPerSeason = 3 },
    @{ Name = "The Office"; Seasons = 2; EpisodesPerSeason = 4 },
    @{ Name = "Game of Thrones"; Seasons = 1; EpisodesPerSeason = 3 },
    @{ Name = "Stranger Things"; Seasons = 2; EpisodesPerSeason = 3 },
    @{ Name = "The Crown"; Seasons = 1; EpisodesPerSeason = 2 }
)

foreach ($show in $shows) {
    $showPath = "$BaseDir\media\shows\$($show.Name)"
    New-Item -ItemType Directory -Path $showPath -Force | Out-Null
    Write-Host "Created show: $($show.Name)"

    for ($season = 1; $season -le $show.Seasons; $season++) {
        $seasonName = "Season {0:D2}" -f $season
        $seasonPath = "$showPath\$seasonName"
        New-Item -ItemType Directory -Path $seasonPath -Force | Out-Null

        for ($episode = 1; $episode -le $show.EpisodesPerSeason; $episode++) {
            $episodeName = "{0} - S{1:D2}E{2:D2}.mkv" -f $show.Name, $season, $episode
            $episodePath = "$seasonPath\$episodeName"

            if (-not (Test-Path $episodePath)) {
                Set-Content -Path $episodePath -Value "Mock episode file: $episodeName"
                Write-Host "  Added episode: $episodeName"
            }
        }
    }
}

# -----------------------------
# Movie data
# -----------------------------
$movies = @(
    @{ Name = "Inception"; Year = 2010 },
    @{ Name = "Interstellar"; Year = 2014 },
    @{ Name = "The Matrix"; Year = 1999 },
    @{ Name = "Gladiator"; Year = 2000 },
    @{ Name = "Oppenheimer"; Year = 2023 }
)

foreach ($movie in $movies) {
    $movieDirName = "{0} ({1})" -f $movie.Name, $movie.Year
    $moviePath = "$BaseDir\media\movies\$movieDirName"
    New-Item -ItemType Directory -Path $moviePath -Force | Out-Null

    $movieFile = "$moviePath\$movieDirName.mkv"
    if (-not (Test-Path $movieFile)) {
        Set-Content -Path $movieFile -Value "Mock movie file: $movieDirName"
        Write-Host "Created movie: $movieDirName"
    }
}

# -----------------------------
# Mock sync script
# -----------------------------
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

# -----------------------------
# Done
# -----------------------------
Write-Host "`nSetup complete! Test data ready in: $BaseDir"
Write-Host "`nTo use local dev mode, set the DEV_MODE environment variable:"
Write-Host "  `$env:DEV_MODE = 'true'"
Write-Host "`nThen run the app:"
Write-Host "  python app.py"
