Write-Host "Este projeto agora é executado por Docker Compose." -ForegroundColor Yellow
Write-Host "Use:" -ForegroundColor Yellow
Write-Host "  docker compose up --build" -ForegroundColor Yellow
Write-Host "Opcional:" -ForegroundColor Yellow
Write-Host "  docker compose --profile ui up --build" -ForegroundColor Yellow
Write-Host "  docker compose --profile logs up --build" -ForegroundColor Yellow
exit 0
