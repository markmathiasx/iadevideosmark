HOTFIX v6 — iadevideosmark

Inclui:
1) Correções do mock (FFmpeg drawtext no Windows + duração mínima + formatos de vídeo).
2) UI: duração mínima (1s) + seleção de formato de vídeo.
3) Automação (scripts):
   - scripts/hf_discover.py: baixa top-100 modelos por task do Hugging Face e grava em config/hf_models_autolist.json
   - scripts/agent_plan.py: usa Ollama (deepseek-r1-14b) para transformar comando em um JSON de job (planejamento).

Observação importante (sobre “pensamento em código aberto”):
- O script gera um PLANO JSON auditável (o que o app vai fazer). Não expõe raciocínio interno passo a passo.

4) scripts/hf_validate.py: valida best-effort (serverless Inference API) e mede latência. Precisa HF_TOKEN.
