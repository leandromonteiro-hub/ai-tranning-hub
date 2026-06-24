import { describe, expect, it } from "vitest";
import { decodeJwtRole } from "../session";

function makeToken(payload: object): string {
  const b64 = Buffer.from(JSON.stringify(payload)).toString("base64url");
  return `header.${b64}.sig`;
}

describe("decodeJwtRole", () => {
  it("lê ADMIN", () => expect(decodeJwtRole(makeToken({ role: "ADMIN" }))).toBe("ADMIN"));
  it("lê ATHLETE", () => expect(decodeJwtRole(makeToken({ role: "ATHLETE" }))).toBe("ATHLETE"));
  it("null para role desconhecido", () =>
    expect(decodeJwtRole(makeToken({ role: "X" }))).toBeNull());
  it("null para token inválido", () => expect(decodeJwtRole("nao-e-jwt")).toBeNull());
});
