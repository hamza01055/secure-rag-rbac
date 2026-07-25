// All backend calls go through the server-side proxy so the JWT stays in an
// HTTP-only cookie the browser never reads. Nothing here sends a role, tenant,
// or clearance — the server derives all of it, and a client that sends them
// gets a 422 rather than a silent override.

export type Principal = {
  user_id: string;
  email: string;
  role: string;
  clearance: number;
  tenant_id: string;
};

export type Citation = {
  chunk_id: string;
  document_id: string;
  filename: string;
  source_page: number | null;
  score: number;
};

export type ChatResponse = {
  answer: string;
  citations: Citation[];
  grounded: boolean | null;
  confidence: number | null;
  stages: Record<string, number> | null;
};

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/proxy${path}`, {
    ...init,
    credentials: "include",
    headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    call<Principal>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }),

  me: () => call<Principal>("/auth/me"),

  logout: () => call<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  ask: (query: string, history: string[] = []) =>
    call<ChatResponse>("/chat", { method: "POST", body: JSON.stringify({ query, history }) }),

  documents: () => call<any[]>("/documents"),

  stats: () => call<any>("/admin/stats"),
};
