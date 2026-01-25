# iadevideosmark — Hotfix Pack (v2)

Corrige os sintomas descritos no bloco de notas:
- Geração de **imagem** falhando (ex.: prompt "foto do pé").
- Geração de **vídeo** com ~3s (mock), agora com **duração configurável** (default 6s).
- Diferencia **modo mock** vs **modo IA** (ex.: ComfyUI).

## Estrutura
- `apps/api`  FastAPI (jobs, providers, safety, arquivos)
- `apps/web`  Vite + React (painel)
- `config/`   providers + policy + workflows ComfyUI
- `scripts/`  setup/dev/validate (PowerShell 5.1 compatível)
- `outputs/`  resultados e logs (criado em runtime)

## Rodar (Windows)
1) Extraia o ZIP no **raiz** do repo: `D:\IANOVA\iadevideosmark` (sobrescrevendo arquivos).
2) `powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1`
3) `powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1`
4) Abra: http://localhost:5173

## Provider IA real (ComfyUI)
- Rode o ComfyUI local (ex.: http://127.0.0.1:8188)
- Configure `.env` (copie de `.env.example`) com `COMFYUI_URL`
- Exporte workflows do ComfyUI e salve em `config\comfyui_workflows` com os nomes indicados.

