HOTFIX3 (corrige SyntaxError no main.py dentro do Docker)

1) Extraia este ZIP por cima do repositório (raiz onde está docker-compose.yml).
2) Rode:
   pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\hotfix3.ps1

   Se preferir (fallback):
   python .\scripts\fix_main.py

3) Reinicie o Docker:
   docker compose down
   docker compose up --build --force-recreate

4) Teste:
   curl http://127.0.0.1:8000/health
