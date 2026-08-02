const RAW_BASE = process.env.API_BASE_URL ?? "http://localhost:8000/api/v1";

/** API base sem barra final. */
export const API_BASE_URL = RAW_BASE.replace(/\/+$/, "");

/**
 * Origem PÚBLICA da requisição, para montar redirects que voltam ao navegador.
 * `request.nextUrl.origin` não serve: atrás do Caddy ele resolve para o
 * hostname interno do container (ex.: "39222f088064:3000") e o redirect morre.
 */
export function publicOrigin(headers: Headers): string {
  const host = headers.get("x-forwarded-host") ?? headers.get("host") ?? "localhost:3000";
  const proto =
    headers.get("x-forwarded-proto") ??
    (/^(localhost|127\.)/.test(host) ? "http" : "https");
  return `${proto}://${host}`;
}

/** Junta a base da API com um path (sem barra inicial) + query string opcional. */
export function resolveApiUrl(path: string, search = ""): string {
  const clean = path.replace(/^\/+/, "");
  const qs = search && !search.startsWith("?") ? `?${search}` : search;
  return `${API_BASE_URL}/${clean}${qs}`;
}
