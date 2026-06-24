import { describe, expect, it } from "vitest";
import { resolveApiUrl } from "../config";

describe("resolveApiUrl", () => {
  it("junta base e path", () => {
    expect(resolveApiUrl("athletes/me")).toMatch(/\/api\/v1\/athletes\/me$/);
  });
  it("tira barras iniciais do path", () => {
    expect(resolveApiUrl("/races")).toMatch(/\/api\/v1\/races$/);
  });
  it("anexa query string", () => {
    expect(resolveApiUrl("recommendations/sample.zwo", "template=vo2max&ftp=250")).toMatch(
      /sample\.zwo\?template=vo2max&ftp=250$/,
    );
  });
});
