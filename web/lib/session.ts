import { cookies } from "next/headers";

export type Role = "ATHLETE" | "ADMIN";
export const TOKEN_COOKIE = "aath_token";

/** Decodifica o payload do JWT (SEM verificar assinatura — só para gatear UI). */
export function decodeJwtRole(token: string): Role | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = Buffer.from(payload, "base64url").toString("utf-8");
    const role = JSON.parse(json).role;
    return role === "ADMIN" || role === "ATHLETE" ? role : null;
  } catch {
    return null;
  }
}

/** Server-only: lê o cookie de auth e decodifica o papel. */
export async function getSession(): Promise<{ token: string; role: Role | null } | null> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  return { token, role: decodeJwtRole(token) };
}
