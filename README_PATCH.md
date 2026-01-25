# Patch Hotfix2 (Docker / SyntaxError main.py)

## O que corrige
- Corrige o `SyntaxError` causado por `try:` colado no final da linha `cmd = base + ... str(out_mp4)] try:` no `apps/api/main.py`.

## Como aplicar (Windows)
1. Extraia este zip na raiz do seu repo: `D:\minhaiateste\MinhaIALAST` (sobrescrevendo arquivos em `scripts\`).
2. Rode o hotfix:
   ```powershell
   pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\hotfix2.ps1
   ```
3. Suba no Docker:
   ```powershell
   docker compose down
   docker compose up --build --force-recreate
   ```
4. Teste:
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8000/health
   ```

## Opcional (WSL/Docker usando muita RAM)
Se o `vmmemWSL` estiver consumindo RAM demais, limite com:
`C:\Users\<SEU_USUARIO>\.wslconfig`

Exemplo:
```ini
[wsl2]
memory=6GB
processors=4
swap=2GB
```

Depois reinicie o WSL:
```powershell
wsl --shutdown
```
