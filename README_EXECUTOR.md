# MinhaIA Local (Executor + UI)

Este patch adiciona um **executador local com interface web** (http://localhost:8000) para você gerar e editar vídeos no estilo *Shorts* sem depender do Clipchamp.

## Rodar (recomendado: Docker)
1. Instale o Docker Desktop.
2. Execute: `scripts\run_bg.cmd`
3. Abra: http://localhost:8000/

Parar: `scripts\stop.cmd`

## Rodar sem Docker (usando seu venv)
1. Garanta `pip install -r apps\api\requirements.txt`
2. Execute: `scripts\run_local_bg.cmd`

Obs.: o script tenta ativar `myenv\.venv\Scripts\activate.bat` ou `myenv\Scripts\activate.bat`.

## Modos (12+)
- shorts_builder (base)
- mock_text_to_video (substituir futuramente por Text-to-Video real)
- mock_image_to_video (substituir futuramente por Image-to-Video real)
- mock_text_to_image
- ffmpeg_resize
- ffmpeg_trim
- ffmpeg_concat
- ffmpeg_merge_audio
- ffmpeg_extract_audio
- ffmpeg_overlay_text
- ffmpeg_watermark
- ffmpeg_burn_subtitles
- ffmpeg_fade

### Parâmetros avançados (JSON)
No campo “Parâmetros avançados (JSON opcional)” você pode passar:
- Trim: `{"start":1.2,"end":9.5}` (ou `{"start":1.2,"duration":8.3}`)
- Watermark: `{"pos":"br","scale_w":140,"margin":20}`
- Overlay text: `{"x":"40","y":"h-160","fontsize":44,"box":1}`
- Extract audio: `{"audio_ext":"wav"}`
- Fade: `{"fade_in":0.7,"fade_out":0.7}`

## Saída
- Outputs por job: `outputs/<job_id>/final.*`
- Logs: `storage/logs/job-<job_id>.log`
