# ============================================================
# NetChaos - MongoDB Seed Script (PowerShell / Windows)
# Usage: .\import_seed.ps1 [-Host localhost] [-Port 27017]
# ============================================================
param(
    [string]$MongoHost = "localhost",
    [int]$Port = 27017
)

$DB = "netchaos"
$SeedDir = $PSScriptRoot

Write-Host "Importing seed data into MongoDB database: $DB" -ForegroundColor Cyan
Write-Host "Host: ${MongoHost}:${Port}" -ForegroundColor Cyan
Write-Host ""

$collections = @(
    "networks",
    "nodes",
    "links",
    "traffic_simulations",
    "chaos_experiments",
    "failure_detections",
    "recovery_events"
)

foreach ($col in $collections) {
    $file = Join-Path $SeedDir "$col.json"
    if (Test-Path $file) {
        Write-Host "Importing $col ..." -ForegroundColor Yellow
        mongoimport `
            --host $MongoHost `
            --port $Port `
            --db $DB `
            --collection $col `
            --file $file `
            --jsonArray `
            --drop
        Write-Host "  OK $col imported" -ForegroundColor Green
    } else {
        Write-Host "  WARNING: $file not found, skipping" -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "Done! Database '$DB' is ready." -ForegroundColor Green
