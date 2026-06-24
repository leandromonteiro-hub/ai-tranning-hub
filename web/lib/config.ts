const RAW_BASE = process.env.API_BASE_URL ?? "http://localhost:8000/api/v1";

/** API base sem barra final. */
export const API_BASE_URL = RAW_BASE.replace(/\/+$/, "");

/** Junta a base da API com um path (sem barra inicial) + query string opcional. */
export function resolveApiUrl(path: string, search = ""): string {
  const clean = path.replace(/^\/+/, "");
  const qs = search && !search.startsWith("?") ? `?${search}` : search;
  return `${API_BASE_URL}/${clean}${qs}`;
}
