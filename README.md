# AI Studio Local (MVP)

Este projeto roda localmente no Windows e NÃO depende de APIs pagas.
Inclui pipelines MOCK para validar a UI e a fila de jobs.

## Rodar
Abra PowerShell:

\\\powershell
cd D:\minhaiateste\MinhaIALAST
.\scripts\setup.ps1
.\scripts\dev.ps1
# em outro terminal:
.\scripts\validate.ps1
\\\

Abra:
- http://127.0.0.1:8000

## Observações
- O modo sensível (toggle) exige consentimento quando ativado.
- Quando desativado, termos explícitos são bloqueados por policy local em config/content_policy.json.
