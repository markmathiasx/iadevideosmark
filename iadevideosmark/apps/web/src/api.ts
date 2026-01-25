export type ProviderInfo = {
  id: string;
  name: string;
  badges: string[];
  capabilities: string[];
  notes?: string;
  available?: boolean;
};

export async function fetchProviders() {
  const r = await fetch("/providers");
  if (!r.ok) throw new Error("Falha ao listar providers");
  return r.json();
}

export async function createJob(form: FormData) {
  const r = await fetch("/jobs", { method: "POST", body: form });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data?.detail || "Falha ao criar job");
  return data;
}

export async function fetchJob(id: string) {
  const r = await fetch(`/jobs/${id}`);
  if (!r.ok) throw new Error("Job não encontrado");
  return r.json();
}

export async function fetchJobs() {
  const r = await fetch(`/jobs?limit=50`);
  if (!r.ok) throw new Error("Falha ao listar jobs");
  return r.json();
}
