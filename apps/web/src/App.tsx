import React, { useEffect, useMemo, useState } from "react";
import { createJob, fetchJob, fetchJobs, fetchProviders, ProviderInfo } from "./api";

type Job = {
  id: string;
  status: string;
  provider: string;
  task: string;
  prompt: string;
  params: any;
  outputs: Record<string, string>;
  error?: string | null;
  meta?: any;
  created_at: number;
};

const TASKS = [
  { id: "text_to_image", label: "Texto → Imagem" },
  { id: "image_edit", label: "Imagem → Editar" },
  { id: "image_upscale", label: "Imagem → Upscale" },
  { id: "text_to_video", label: "Texto → Vídeo" },
  { id: "image_to_video", label: "Imagem → Vídeo" },
  { id: "video_edit", label: "Vídeo → Editar" },
];

function pillClass(ok?: boolean, warn?: boolean) {
  if (ok) return "pill ok";
  if (warn) return "pill warn";
  return "pill";
}

export default function App() {
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [defaultProvider, setDefaultProvider] = useState<string>("mock");
  const [provider, setProvider] = useState<string>("mock");
  const [task, setTask] = useState<string>("text_to_video");
  const [prompt, setPrompt] = useState<string>("um cachorro correndo no parque, câmera baixa, luz do pôr do sol");
  const [duration, setDuration] = useState<number>(6);
  const [fps, setFps] = useState<number>(24);
  const [width, setWidth] = useState<number>(1280);
  const [height, setHeight] = useState<number>(720);
  const [outputFormat, setOutputFormat] = useState<string>("jpeg");
  const [videoFormat, setVideoFormat] = useState<string>("mp4");
  const [jpegQuality, setJpegQuality] = useState<number>(95);
  const [webpQuality, setWebpQuality] = useState<number>(90);
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [videoFile, setVideoFile] = useState<File | null>(null);

  const [busy, setBusy] = useState(false);
  const [currentJob, setCurrentJob] = useState<Job | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchProviders();
        setProviders(data.providers || []);
        setDefaultProvider(data.default_provider || "mock");
        setProvider(data.default_provider || "mock");
      } catch (e: any) {
        setError(e.message || String(e));
      }
    })();
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const data = await fetchJobs();
        setJobs(data.jobs || []);
      } catch {}
    })();
  }, [currentJob?.id]);

  const selectedProvider = useMemo(
    () => providers.find((p) => p.id === provider),
    [providers, provider]
  );

  const canUseImage = task.startsWith("image_") || task === "image_to_video";
  const canUseVideo = task === "video_edit";
  const isImageTask = task === "text_to_image" || task === "image_edit" || task === "image_upscale";
  const isVideoTask = task === "text_to_video" || task === "image_to_video" || task === "video_edit";

  // defaults por tipo de task (alta resolução por padrão)
  useEffect(() => {
    if (isImageTask) {
      setWidth((w) => (w < 900 ? 1024 : w));
      setHeight((h) => (h < 900 ? 1024 : h));
      if (!outputFormat) setOutputFormat("jpeg");
    } else if (isVideoTask) {
      setWidth((w) => (w < 1100 ? 1280 : w));
      setHeight((h) => (h < 700 ? 720 : h));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task]);

  async function submit() {
    setBusy(true);
    setError(null);
    setCurrentJob(null);
    try {
      const params: any = { width, height, duration_s: duration, fps };
      if (isImageTask) {
        params.output_format = outputFormat;
        params.jpeg_quality = jpegQuality;
        params.webp_quality = webpQuality;
      }
      if (isVideoTask) {
        params.video_format = videoFormat;
      }
      const form = new FormData();
      form.set("provider", provider);
      form.set("task", task);
      form.set("prompt", prompt);
      form.set("params", JSON.stringify(params));
      if (imageFile) form.set("image", imageFile);
      if (videoFile) form.set("video", videoFile);

      const created = await createJob(form);
      const id = created.id as string;

      // poll
      let j: Job | null = null;
      for (let i = 0; i < 240; i++) {
        j = await fetchJob(id);
        setCurrentJob(j);
        if (j.status === "succeeded" || j.status === "failed") break;
        await new Promise((r) => setTimeout(r, 1000));
      }
      if (j && j.status === "failed") {
        setError(j.error || "Falha no job");
      }
    } catch (e: any) {
      setError(e.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  function renderResult(job: Job) {
    const video = job.outputs?.video;
    const image = job.outputs?.image;
    const history = job.outputs?.history;

    return (
      <div className="card">
        <div className="row" style={{ alignItems: "center" }}>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700 }}>
              Resultado — {job.status}
            </div>
            <div className="muted">
              provider: {job.provider} · task: {job.task} · id: {job.id}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <span className={pillClass(job.status === "succeeded", job.status === "running")}>
              {job.status}
            </span>
            <span className="pill">{job.meta?.mode || "n/a"}</span>
          </div>
        </div>

        {job.error ? (
          <div className="card" style={{ borderColor: "#c33", marginTop: 12 }}>
            <div style={{ fontWeight: 700 }}>Erro</div>
            <div className="muted">{job.error}</div>
          </div>
        ) : null}

        {video ? (
          <div style={{ marginTop: 12 }}>
            <video className="media" controls src={`/outputs/${video}`} />
            <div className="muted">/outputs/{video}</div>
            <a
              className="muted"
              href={`/outputs/${video}`}
              download={`${job.task}_${job.id.slice(0, 8)}${video.includes(".") ? video.slice(video.lastIndexOf(".")) : ".mp4"}`}
              target="_blank"
              rel="noreferrer"
            >
              Baixar arquivo
            </a>
          </div>
        ) : null}

        {image ? (
          <div style={{ marginTop: 12 }}>
            <img className="media" src={`/outputs/${image}`} />
            <div className="muted">/outputs/{image}</div>
            <a
              className="muted"
              href={`/outputs/${image}`}
              download={`${job.task}_${job.id.slice(0, 8)}${image.includes(".") ? image.slice(image.lastIndexOf(".")) : ".jpg"}`}
              target="_blank"
              rel="noreferrer"
            >
              Baixar arquivo
            </a>
          </div>
        ) : null}

        {history ? (
          <div style={{ marginTop: 12 }}>
            <a className="muted" href={`/outputs/${history}`} target="_blank">
              Abrir histórico ComfyUI (JSON)
            </a>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <div className="container">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
        <div>
          <div style={{ fontSize: 20, fontWeight: 800 }}>iadevideosmark</div>
          <div className="muted">Painel local — providers plugáveis — modo mock/IA</div>
        </div>
        <div>
          <span className={pillClass(!!selectedProvider?.available, !selectedProvider?.available)}>
            {selectedProvider?.available ? "provider disponível" : "provider indisponível"}
          </span>
          <span className="pill">{selectedProvider?.id || "n/a"}</span>
        </div>
      </div>

      {error ? (
        <div className="card" style={{ borderColor: "#c33", marginTop: 12 }}>
          <div style={{ fontWeight: 700 }}>Erro</div>
          <div className="muted">{error}</div>
        </div>
      ) : null}

      <div className="grid" style={{ marginTop: 16 }}>
        <div className="card">
          <div style={{ fontSize: 14, fontWeight: 700 }}>Configuração</div>

          <label>Provider</label>
          <select value={provider} onChange={(e) => setProvider(e.target.value)}>
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.id})
              </option>
            ))}
          </select>
          <div className="muted">
            {selectedProvider?.badges?.map((b) => (
              <span key={b} className="pill">{b}</span>
            ))}
          </div>
          <div className="muted" style={{ marginTop: 6 }}>
            {selectedProvider?.notes}
          </div>

          <label>Task</label>
          <select value={task} onChange={(e) => setTask(e.target.value)}>
            {TASKS.map((t) => (
              <option key={t.id} value={t.id}>{t.label}</option>
            ))}
          </select>

          <label>Prompt</label>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} />

          {isImageTask ? (
            <div className="row">
              <div>
                <label>Formato de saída</label>
                <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value)}>
                  <option value="jpeg">JPEG (recomendado)</option>
                  <option value="png">PNG</option>
                  <option value="webp">WEBP</option>
                </select>
              </div>
              {outputFormat === "jpeg" ? (
                <div>
                  <label>Qualidade JPEG</label>
                  <input type="number" value={jpegQuality} min={60} max={100} onChange={(e) => setJpegQuality(parseInt(e.target.value || "95", 10))} />
                </div>
              ) : null}
              {outputFormat === "webp" ? (
                <div>
                  <label>Qualidade WEBP</label>
                  <input type="number" value={webpQuality} min={50} max={100} onChange={(e) => setWebpQuality(parseInt(e.target.value || "90", 10))} />
                </div>
              ) : null}
            </div>
          ) : null}

          {isVideoTask ? (
            <div className="row">
              <div>
                <label>Formato do vídeo</label>
                <select value={videoFormat} onChange={(e) => setVideoFormat(e.target.value)}>
                  <option value="mp4">MP4 (recomendado)</option>
                  <option value="webm">WEBM</option>
                  <option value="gif">GIF</option>
                </select>
              </div>
            </div>
          ) : null}
              <div>
              <label>Width</label>
              <input type="number" value={width} onChange={(e) => setWidth(parseInt(e.target.value || "0", 10))} />
            </div>
            <div>
              <label>Height</label>
              <input type="number" value={height} onChange={(e) => setHeight(parseInt(e.target.value || "0", 10))} />
            </div>
          </div>
            <div className="row">
              <div>
              <label>Duração (s)</label>
              <input type="number" min={1} max={60} step={1} value={duration} onChange={(e) => {
                const v = parseFloat(e.target.value || "0");
                const vv = Number.isFinite(v) ? v : 0;
                setDuration(Math.max(1, Math.min(60, vv || 1)));
              }} />
            </div>
            <div>
              <label>FPS</label>
              <input type="number" value={fps} onChange={(e) => setFps(parseInt(e.target.value || "0", 10))} />
            </div>
          </div>

          <label>Upload (opcional)</label>
          <div className="row">
            <input
              type="file"
              accept="image/*"
              disabled={!canUseImage}
              onChange={(e) => setImageFile(e.target.files?.[0] || null)}
            />
            <input
              type="file"
              accept="video/*"
              disabled={!canUseVideo}
              onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
            />
          </div>
          <div className="muted">
            Upload habilitado somente para tasks que aceitam imagem/vídeo.
          </div>

          <div style={{ marginTop: 12 }}>
            <button onClick={submit} disabled={busy}>
              {busy ? "Gerando..." : "Gerar"}
            </button>
          </div>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {currentJob ? renderResult(currentJob) : (
            <div className="card">
              <div style={{ fontSize: 14, fontWeight: 700 }}>Resultado</div>
              <div className="muted">Nenhum job ainda. Use "Gerar".</div>
            </div>
          )}

          <div className="card">
            <div style={{ fontSize: 14, fontWeight: 700 }}>Histórico</div>
            <div className="muted">Últimos jobs (máx 50)</div>
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 8 }}>
              {jobs.slice(0, 12).map((j) => (
                <div key={j.id} style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                  <div className="muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {j.task} · {j.provider} · {j.id.slice(0, 8)}
                  </div>
                  <div>
                    <span className={pillClass(j.status === "succeeded", j.status === "failed")}>
                      {j.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>

      <div className="card" style={{ marginTop: 16 }}>
        <div style={{ fontSize: 14, fontWeight: 700 }}>Notas rápidas</div>
        <ul className="muted">
          <li>Se estiver vendo vídeos curtos (ex.: 3s), ajuste a duração; no modo mock o default é 6s.</li>
          <li>Se imagem falhar, confira a mensagem de erro e se o provider suporta a task selecionada.</li>
          <li>Para IA real (ComfyUI), configure workflows em <code>config/comfyui_workflows</code>.</li>
        </ul>
      </div>
    </div>
  );
}
