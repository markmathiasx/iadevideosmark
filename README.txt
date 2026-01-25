Como usar (Windows + Docker Desktop)

1) Extraia estes arquivos na RAIZ do seu repositório (ex.: D:\minhaiateste\MinhaIALAST):
   - Dockerfile
   - docker-compose.yml
   - .dockerignore

2) Abra PowerShell 7 (pwsh) na raiz do repo e rode:
   docker compose up --build

3) Em outro terminal, teste:
   Invoke-RestMethod http://127.0.0.1:8000/health

4) Para parar:
   Ctrl+C no terminal do compose e depois:
   docker compose down

Se a porta 8000 estiver ocupada:
- Edite docker-compose.yml e troque "8000:8000" para "8001:8000"
- Acesse http://127.0.0.1:8001/health
