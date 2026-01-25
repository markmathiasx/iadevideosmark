HOTFIX v8 — iadevideosmark

O que este hotfix corrige/entrega:
- Corrige mock provider (syntax + FFmpeg drawtext no Windows) e força duração mínima (>=1s).
- Default de imagem em JPEG (qualidade 95) e suporte a "perfil" (draft/high/ultra).
- UI redesenhada (mais profissional), com:
  - pasta de saída (subdir)
  - aba Diagnóstico
  - seção "Assistente (comando natural)" que usa /api/agent/plan (Ollama/OpenAI)
- Dockerfile + docker-compose.yml (API 8000, UI opcional 5173, logs_viewer opcional 8080).
- logging_service (logs_viewer) para listar outputs/jobs.
- Scripts PowerShell desabilitados (orienta usar Docker).
- Scripts HF: hf_discover.py e hf_validate.py.
- Script de planejamento via Ollama: agent_plan.py (DeepSeek R1-14B).

Como aplicar:
1) EXTRAIA este zip NA RAIZ DO REPO (onde existe o Dockerfile atual).
2) Substitua arquivos quando o Windows perguntar.

Como executar (Docker):
- API: docker compose up --build
- UI (opcional): docker compose --profile ui up --build
- Logs (opcional): docker compose --profile logs up --build

ComfyUI:
- O provider ComfyUI ainda exige workflows em config/comfyui_workflows/*.json
