"use client";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

async function handle(res: Response): Promise<Response> {
  if (res.status === 401) {
    // Sessão expirada/ausente — derruba e volta ao login.
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch {}
    if (typeof window !== "undefined") window.location.href = "/login";
    throw new ApiError(401, "Sessão expirada");
  }
  return res;
}

/** Chama o proxy BFF. `path` é o caminho do FastAPI sem o /api/v1. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const clean = path.replace(/^\/+/, "");
  const res = await fetch(`/api/proxy/${clean}`, init);
  return handle(res);
}

/** Fetcher do SWR: GET + JSON. */
export async function jsonFetcher(path: string): Promise<unknown> {
  const res = await apiFetch(path);
  if (!res.ok) throw new ApiError(res.status, await res.text());
  return res.json();
}
