$ErrorActionPreference="Stop"
Set-Location $PSScriptRoot
Write-Host "Starting SARCADE Demo..."
docker compose -f docker-compose.demo.yml up -d --build postgres server
Write-Host "Waiting for server..."
Start-Sleep -Seconds 8
Write-Host "API: http://localhost:8000/docs"
Write-Host "To simulate 4 operators:"
Write-Host "docker compose -f docker-compose.demo.yml --profile simulate run --rm simulator"
Write-Host "To verify idempotence:"
Write-Host "docker compose -f docker-compose.demo.yml run --rm simulator python verify.py"
