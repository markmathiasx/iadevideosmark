import React, { useEffect, useMemo, useState } from "react";

type Provider = { name: string; label?: string; modes?: string[]; status?: string };
type JobCreate = {
  provider: string;
  task: string;
  prompt: string;
  width: number;
  height: number;
  duration_s?: number;
  fps?: number;
  output_format?: string;     // "jpeg"|"png"|"mp4"
  output_profile?: string;    // "draft"|"high"|"ultra"
  output_subdir?: string;     // relative under ./outputs/
  jpeg_quality?: number;      // 60..100
};

type JobStatus = {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  provider?: string;
  task?: string;
  output_path?: string;
  error?: string;
  created_at?: string;
};

const API_BASE = (import.meta as any).env?.VITE_API_BASE || "";

function cx(...xs: Array<string | false | null | undefined>) {
  return xs.filter(Boolean).join(" ");
}

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

async function apiPost<T>(path: string, body: any): Promise<T> {
  const r = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await r.text();
  if (!r.ok) throw new Error(text || `${r.status} ${r.statusText}`);
  return text ? JSON.parse(text) : ({} as any);
}

function nowIso() {
  return new Date().toISOString();
}

export default function App() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [provider, setProvider] = useState("mock");
  const [task, setTask] = useState("image_edit");

  const [prompt, setPrompt] = useState("ao invés dele estar segurando cerveja é um sorvete");
  const [natural, setNatural] = useState("bota um sorvete no lugar da cerveja");

  const [width, setWidth] = useState(1280);
  const [height, setHeight] = useState(1024);
  const [duration, setDuration] = useState(6);
  const [fps, setFps] = useState(24);

  const [outputProfile, setOutputProfile] = useState<"draft" | "high" | "ultra">("high");
  const [outputFormat, setOutputFormat] = useState<"jpeg" | "png" | "mp4">("jpeg");
  const [jpegQuality, setJpegQuality] = useState(95);
  const [outputSubdir, setOutputSubdir] = useState("jobs");

  const [uploadFile, setUploadFile] = useState<File | null>(null);

  const [activeJob, setActiveJob] = useState<JobStatus | null>(null);
  const [history, setHistory] = useState<JobStatus[]>([]);
  const [tab, setTab] = useState<"run" | "history" | "diagnostics">("run");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const isVideoTask = useMemo(() => ["text_to_video", "image_to_video"].includes(task), [task]);
  const needsUpload = useMemo(() => ["image_edit", "image_upscale", "image_to_video"].includes(task), [task]);

  useEffect(() => {
    (async () => {
      try {
        const ps = await apiGet<Provider[]>("/api/providers");
        setProviders(ps || []);
        if (ps?.length && !ps.find(p => p.name === provider)) setProvider(ps[0].name);
      } catch (e: any) {
        // keep UI usable offline
        setProviders([{ name: "mock", label: "Mock (offline)" }]);
      }
    })();
  }, []);

  async function createJob() {
    setErr(null);
    setBusy(true);
    try {
      // NOTE: upload endpoint can vary; for now we require backend to accept local file already available server-side.
      // Many deployments already support multipart upload. If yours does, adapt backend accordingly.
      const payload: JobCreate = {
        provider,
        task,
        prompt,
        width,
        height,
        duration_s: isVideoTask ? Math.max(1, duration || 6) : undefined,
        fps: isVideoTask ? Math.max(1, fps || 24) : undefined,
        output_format: isVideoTask ? "mp4" : outputFormat,
        output_profile: outputProfile,
        output_subdir: outputSubdir,
        jpeg_quality: outputFormat === "jpeg" ? Math.max(60, Math.min(100, jpegQuality)) : undefined,
      };

      if (needsUpload && !uploadFile) {
        throw new Error("Esta task exige upload de imagem. Selecione um arquivo antes de gerar.");
      }

      // If backend supports upload, it should accept upload_id or upload_path.
      // For now we pass filename and rely on backend mapping (mock/local dev).
      if (needsUpload && uploadFile) (payload as any).upload_filename = uploadFile.name;

      const job = await apiPost<JobStatus>("/api/jobs", payload);
      setActiveJob(job);
      setHistory(h => [job, ...h].slice(0, 50));
      setTab("run");
      await poll(job.id);
    } catch (e: any) {
      setErr(String(e?.message || e));
    } finally {
      setBusy(false);
    }
  }

  async function poll(jobId: string) {
    const start = Date.now();
    while (Date.now() - start < 1000 * 60 * 8) {
      try {
        const st = await apiGet<JobStatus>(`/api/jobs/${jobId}`);
        setActiveJob(st);
        setHistory(h => [st, ...h.filter(x => x.id !== st.id)].slice(0, 50));
        if (st.status === "succeeded" || st.status === "failed") return;
      } catch {}
      await new Promise(r => setTimeout(r, 900));
    }
  }

  async function interpretNatural() {
    setErr(null);
    setBusy(true);
    try {
      // optional endpoint: /api/agent/plan
      const plan = await apiPost<any>("/api/agent/plan", {
        text: natural,
        hint_task: task,
        hint_provider: provider,
      });
      if (plan?.task) setTask(plan.task);
      if (plan?.provider) setProvider(plan.provider);
      if (plan?.prompt) setPrompt(plan.prompt);
      if (plan?.width) setWidth(plan.width);
      if (plan?.height) setHeight(plan.height);
      if (plan?.duration_s) setDuration(plan.duration_s);
      if (plan?.fps) setFps(plan.fps);
      if (plan?.output_format) setOutputFormat(plan.output_format);
      if (plan?.output_profile) setOutputProfile(plan.output_profile);
      if (plan?.output_subdir) setOutputSubdir(plan.output_subdir);
    } catch (e: any) {
      setErr("Endpoint /api/agent/plan não disponível. Use manualmente ou ative o provider Ollama/OpenAI no backend.");
    } finally {
      setBusy(false);
    }
  }

  const activeOutputUrl = useMemo(() => {
    if (!activeJob?.output_path) return null;
    // Backend often returns absolute/relative path in disk. UI expects /outputs path.
    const p = activeJob.output_path.replaceAll("\\", "/");
    const idx = p.lastIndexOf("/outputs/");
    if (idx >= 0) return `${API_BASE}${p.slice(idx)}`;
    // fallback: assume output_path already API-served
    if (p.startsWith("/")) return `${API_BASE}${p}`;
    return `${API_BASE}/${p}`;
  }, [activeJob]);

  const providerLabel = useMemo(() => providers.find(p => p.name === provider)?.label || provider, [providers, provider]);
  const providerIsMock = useMemo(() => provider === "mock" || providerLabel.toLowerCase().includes("mock"), [provider, providerLabel]);

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <div style={styles.brand}>
          <div style={styles.brandTitle}>iadevideosmark</div>
          <div style={styles.brandSub}>Painel local — providers plugáveis — modo mock/IA</div>
        </div>
        <div style={styles.headerRight}>
          <span style={styles.pill}>
            provider: <b style={styles.pillValue}>{providerLabel}</b>
          </span>
          <span style={styles.pillMuted}>{nowIso().slice(0, 19).replace("T", " ")}</span>
        </div>
      </header>

      <main style={styles.main}>
        <section style={styles.card}>
          <div style={styles.cardTitle}>Configuração</div>

          <div style={styles.grid2}>
            <div>
              <label style={styles.label}>Provider</label>
              <select style={styles.select} value={provider} onChange={e => setProvider(e.target.value)}>
                {providers.map(p => (
                  <option key={p.name} value={p.name}>
                    {p.label || p.name}
                  </option>
                ))}
              </select>
              <div style={styles.help}>
                {providerIsMock ? (
                  <span>
                    Mock é apenas placeholder (Pillow/FFmpeg). Para resultado “igual ao ChatGPT”, use provider real (ComfyUI/HF/OpenAI).
                  </span>
                ) : (
                  <span>Provider real selecionado.</span>
                )}
              </div>
            </div>

            <div>
              <label style={styles.label}>Task</label>
              <select style={styles.select} value={task} onChange={e => setTask(e.target.value)}>
                <option value="text_to_image">Texto → Imagem</option>
                <option value="image_edit">Imagem → Editar</option>
                <option value="image_upscale">Imagem → Upscale</option>
                <option value="image_to_video">Imagem → Vídeo</option>
                <option value="text_to_video">Texto → Vídeo</option>
              </select>
              <div style={styles.help}>Se vídeo estiver curto/errado, ajuste duração e FPS.</div>
            </div>
          </div>

          <div style={styles.sep} />

          <div>
            <label style={styles.label}>Assistente (comando natural)</label>
            <textarea style={styles.textareaSmall} value={natural} onChange={e => setNatural(e.target.value)} />
            <div style={styles.row}>
              <button style={styles.buttonSecondary} disabled={busy} onClick={interpretNatural}>
                Interpretar (Ollama/OpenAI)
              </button>
              <div style={styles.help}>
                Transforma o comando em parâmetros do job (JSON). Requer backend com endpoint /api/agent/plan.
              </div>
            </div>
          </div>

          <div style={styles.sep} />

          <div>
            <label style={styles.label}>Prompt</label>
            <textarea style={styles.textarea} value={prompt} onChange={e => setPrompt(e.target.value)} />
          </div>

          <div style={styles.grid4}>
            <div>
              <label style={styles.label}>Width</label>
              <input style={styles.input} type="number" value={width} onChange={e => setWidth(parseInt(e.target.value || "0", 10))} />
            </div>
            <div>
              <label style={styles.label}>Height</label>
              <input style={styles.input} type="number" value={height} onChange={e => setHeight(parseInt(e.target.value || "0", 10))} />
            </div>
            <div>
              <label style={styles.label}>Duração (s)</label>
              <input style={styles.input} type="number" value={duration} onChange={e => setDuration(parseFloat(e.target.value || "0"))} disabled={!isVideoTask} />
            </div>
            <div>
              <label style={styles.label}>FPS</label>
              <input style={styles.input} type="number" value={fps} onChange={e => setFps(parseInt(e.target.value || "0", 10))} disabled={!isVideoTask} />
            </div>
          </div>

          <div style={styles.grid4}>
            <div>
              <label style={styles.label}>Perfil</label>
              <select style={styles.select} value={outputProfile} onChange={e => setOutputProfile(e.target.value as any)}>
                <option value="draft">Draft</option>
                <option value="high">High</option>
                <option value="ultra">Ultra</option>
              </select>
            </div>

            <div>
              <label style={styles.label}>Formato saída</label>
              <select style={styles.select} value={isVideoTask ? "mp4" : outputFormat} onChange={e => setOutputFormat(e.target.value as any)} disabled={isVideoTask}>
                <option value="jpeg">JPEG</option>
                <option value="png">PNG</option>
              </select>
            </div>

            <div>
              <label style={styles.label}>Qualidade JPEG</label>
              <input style={styles.input} type="number" value={jpegQuality} onChange={e => setJpegQuality(parseInt(e.target.value || "95", 10))} disabled={isVideoTask || outputFormat !== "jpeg"} />
            </div>

            <div>
              <label style={styles.label}>Pasta de saída</label>
              <input style={styles.input} value={outputSubdir} onChange={e => setOutputSubdir(e.target.value)} />
              <div style={styles.help}>Relativa a ./outputs. Ex.: jobs (padrão), export, testes.</div>
            </div>
          </div>

          <div style={styles.sep} />

          <div>
            <label style={styles.label}>Upload (opcional/obrigatório por task)</label>
            <div style={styles.row}>
              <input
                style={styles.inputFile}
                type="file"
                accept="image/*"
                onChange={e => setUploadFile(e.target.files?.[0] || null)}
              />
              <div style={styles.help}>
                {needsUpload ? "Obrigatório para esta task." : "Opcional."} (Browser não permite escolher pasta de saída nativa; usamos subdir.)
              </div>
            </div>
          </div>

          <div style={{ ...styles.row, marginTop: 16 }}>
            <button style={styles.button} onClick={createJob} disabled={busy}>
              {busy ? "Processando..." : "Gerar"}
            </button>
            {err ? <div style={styles.error}>{err}</div> : null}
          </div>
        </section>

        <section style={styles.card}>
          <div style={styles.cardTitleRow}>
            <div style={styles.cardTitle}>Resultado</div>
            <div style={styles.tabs}>
              <button style={cxTab(tab === "run")} onClick={() => setTab("run")}>Atual</button>
              <button style={cxTab(tab === "history")} onClick={() => setTab("history")}>Histórico</button>
              <button style={cxTab(tab === "diagnostics")} onClick={() => setTab("diagnostics")}>Diagnóstico</button>
            </div>
          </div>

          {tab === "run" && (
            <>
              <div style={styles.resultMeta}>
                <div><b>Status:</b> {activeJob?.status || "-"}</div>
                <div><b>Provider:</b> {activeJob?.provider || provider}</div>
                <div><b>Task:</b> {activeJob?.task || task}</div>
              </div>

              {activeJob?.error ? <div style={styles.error}>{activeJob.error}</div> : null}

              {activeOutputUrl ? (
                <div style={styles.previewWrap}>
                  {activeJob?.output_path?.toLowerCase().endsWith(".mp4") ? (
                    <video style={styles.video} controls src={activeOutputUrl} />
                  ) : (
                    <img style={styles.img} src={activeOutputUrl} />
                  )}

                  <div style={styles.row}>
                    <a style={styles.linkBtn} href={activeOutputUrl} download>
                      Download
                    </a>
                    <span style={styles.help}>
                      Se estiver baixando .gitkeep, você está clicando no arquivo errado; o output real fica em outputs/jobs/&lt;id&gt;/...
                    </span>
                  </div>
                </div>
              ) : (
                <div style={styles.placeholder}>
                  Nenhum output ainda. Gere um job para visualizar.
                </div>
              )}
            </>
          )}

          {tab === "history" && (
            <div style={styles.history}>
              {history.length === 0 ? <div style={styles.placeholder}>Sem histórico.</div> : null}
              {history.map(h => (
                <div key={h.id} style={styles.historyRow}>
                  <div style={styles.historyLeft}>
                    <div style={styles.historyId}>{h.id}</div>
                    <div style={styles.historySmall}>
                      {h.task} • {h.provider} • {h.status}
                    </div>
                  </div>
                  <button style={styles.buttonSecondary} onClick={() => poll(h.id)}>
                    Abrir
                  </button>
                </div>
              ))}
            </div>
          )}

          {tab === "diagnostics" && (
            <Diagnostics />
          )}
        </section>
      </main>

      <footer style={styles.footer}>
        <div style={styles.footerBox}>
          <div style={styles.footerTitle}>Notas rápidas</div>
          <ul style={styles.ul}>
            <li>Mock não entende imagem. Para edição real, configure ComfyUI, Hugging Face ou OpenAI.</li>
            <li>ComfyUI: exporte workflows JSON para <code>config/comfyui_workflows/</code> (ex.: <code>text_to_image.json</code>).</li>
            <li>Vídeos: duração mínima 1s; se falhar no Windows, verifique FFmpeg e fontes.</li>
          </ul>
        </div>
      </footer>
    </div>
  );
}

function cxTab(active: boolean) {
  return cx("tab", active && "tabActive");
}

function Diagnostics() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const p = await apiGet<any>("/api/providers");
        setData({ providers: p });
      } catch (e: any) {
        setErr("Falha ao acessar /api/providers. Verifique se a API está em 8000.");
      }
    })();
  }, []);

  if (err) return <div style={styles.error}>{err}</div>;
  if (!data) return <div style={styles.placeholder}>Carregando…</div>;

  return (
    <div style={styles.diag}>
      <div style={styles.diagTitle}>Providers</div>
      <pre style={styles.pre}>{JSON.stringify(data.providers, null, 2)}</pre>
      <div style={styles.diagTitle}>Checklist</div>
      <ul style={styles.ul}>
        <li><code>http://localhost:8000/api/providers</code> deve responder.</li>
        <li><code>outputs/</code> deve existir e ser gravável.</li>
        <li>Se ComfyUI estiver habilitado, o servidor deve estar acessível (por padrão 8188).</li>
      </ul>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "radial-gradient(1200px 800px at 20% 10%, #1d1d23 0%, #0f0f12 55%, #0b0b0d 100%)",
    color: "#e9e9ee",
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    padding: "18px 22px",
    borderBottom: "1px solid rgba(255,255,255,0.06)",
    position: "sticky",
    top: 0,
    backdropFilter: "blur(8px)",
    background: "rgba(12,12,14,0.75)",
    zIndex: 5,
  },
  brand: { display: "flex", flexDirection: "column", gap: 4 },
  brandTitle: { fontSize: 18, fontWeight: 700, letterSpacing: 0.4 },
  brandSub: { fontSize: 12, opacity: 0.7 },
  headerRight: { display: "flex", gap: 10, alignItems: "center" },
  pill: {
    padding: "6px 10px",
    borderRadius: 999,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(255,255,255,0.04)",
    fontSize: 12,
  },
  pillValue: { fontWeight: 700 },
  pillMuted: { fontSize: 12, opacity: 0.6 },
  main: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr",
    gap: 16,
    padding: 16,
    alignItems: "start",
    maxWidth: 1280,
    margin: "0 auto",
  },
  card: {
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(16,16,20,0.72)",
    borderRadius: 16,
    padding: 16,
    boxShadow: "0 10px 30px rgba(0,0,0,0.25)",
  },
  cardTitle: { fontSize: 14, fontWeight: 700, marginBottom: 12, opacity: 0.95 },
  cardTitleRow: { display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, marginBottom: 8 },
  tabs: { display: "flex", gap: 8 },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 },
  grid4: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginTop: 10 },
  label: { fontSize: 12, opacity: 0.75, display: "block", marginBottom: 6 },
  input: {
    width: "100%",
    padding: "10px 10px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(255,255,255,0.03)",
    color: "#e9e9ee",
    outline: "none",
  },
  inputFile: { width: "100%", color: "#e9e9ee" },
  select: {
    width: "100%",
    padding: "10px 10px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(10,10,12,0.6)",
    color: "#e9e9ee",
    outline: "none",
  },
  textarea: {
    width: "100%",
    minHeight: 130,
    padding: 12,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(255,255,255,0.03)",
    color: "#e9e9ee",
    outline: "none",
    resize: "vertical",
  },
  textareaSmall: {
    width: "100%",
    minHeight: 70,
    padding: 12,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(255,255,255,0.03)",
    color: "#e9e9ee",
    outline: "none",
    resize: "vertical",
  },
  help: { fontSize: 12, opacity: 0.65, marginTop: 6 },
  sep: { height: 1, background: "rgba(255,255,255,0.07)", margin: "14px 0" },
  row: { display: "flex", alignItems: "center", gap: 12 },
  button: {
    padding: "10px 14px",
    borderRadius: 12,
    border: "1px solid rgba(120,255,170,0.35)",
    background: "rgba(22,120,70,0.35)",
    color: "#e9e9ee",
    fontWeight: 700,
    cursor: "pointer",
  },
  buttonSecondary: {
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(255,255,255,0.04)",
    color: "#e9e9ee",
    cursor: "pointer",
    fontWeight: 600,
  },
  error: {
    marginLeft: 8,
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,90,90,0.35)",
    background: "rgba(160,30,30,0.20)",
    color: "#ffd7d7",
    fontSize: 12,
    flex: 1,
  },
  resultMeta: { display: "flex", gap: 14, fontSize: 12, opacity: 0.8, marginBottom: 10 },
  previewWrap: { display: "flex", flexDirection: "column", gap: 12 },
  img: {
    width: "100%",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(0,0,0,0.25)",
  },
  video: {
    width: "100%",
    borderRadius: 14,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(0,0,0,0.25)",
  },
  placeholder: {
    padding: 14,
    borderRadius: 14,
    border: "1px dashed rgba(255,255,255,0.18)",
    opacity: 0.75,
    fontSize: 12,
  },
  linkBtn: {
    display: "inline-block",
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.12)",
    background: "rgba(255,255,255,0.04)",
    color: "#e9e9ee",
    textDecoration: "none",
    fontWeight: 600,
  },
  history: { display: "flex", flexDirection: "column", gap: 10, marginTop: 8 },
  historyRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12,
    padding: 10,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(255,255,255,0.03)",
  },
  historyLeft: { display: "flex", flexDirection: "column", gap: 4 },
  historyId: { fontSize: 12, fontWeight: 700 },
  historySmall: { fontSize: 12, opacity: 0.65 },
  diag: { display: "flex", flexDirection: "column", gap: 10, marginTop: 10 },
  diagTitle: { fontSize: 12, fontWeight: 700, opacity: 0.9 },
  pre: {
    padding: 12,
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.10)",
    background: "rgba(0,0,0,0.25)",
    overflow: "auto",
    maxHeight: 320,
    fontSize: 12,
  },
  footer: { padding: "0 16px 18px", maxWidth: 1280, margin: "0 auto" },
  footerBox: {
    marginTop: 8,
    padding: 14,
    borderRadius: 16,
    border: "1px solid rgba(255,255,255,0.08)",
    background: "rgba(16,16,20,0.5)",
  },
  footerTitle: { fontSize: 12, fontWeight: 700, marginBottom: 8, opacity: 0.9 },
  ul: { margin: 0, paddingLeft: 18, fontSize: 12, opacity: 0.75, lineHeight: 1.6 },
};

// simple tab classes using inline style injection (Vite will keep it)
const styleEl = document.createElement("style");
styleEl.textContent = `
  .tab{ padding:8px 10px; border-radius:12px; border:1px solid rgba(255,255,255,0.12); background:rgba(255,255,255,0.04); color:#e9e9ee; cursor:pointer; font-weight:600; }
  .tabActive{ border-color: rgba(120,255,170,0.40); background: rgba(22,120,70,0.25); }
`;
document.head.appendChild(styleEl);
