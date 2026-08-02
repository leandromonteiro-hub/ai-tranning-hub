import { describe, expect, it } from "vitest";
import { publicOrigin, resolveApiUrl } from "../config";

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

describe("publicOrigin", () => {
  it("usa o Host que o proxy repassa, com https", () => {
    const h = new Headers({ host: "62-171-128-103.sslip.io" });
    expect(publicOrigin(h)).toBe("https://62-171-128-103.sslip.io");
  });
  it("prefere x-forwarded-host quando presente", () => {
    const h = new Headers({ host: "39222f088064:3000", "x-forwarded-host": "meusite.com" });
    expect(publicOrigin(h)).toBe("https://meusite.com");
  });
  it("respeita x-forwarded-proto", () => {
    const h = new Headers({ host: "meusite.com", "x-forwarded-proto": "http" });
    expect(publicOrigin(h)).toBe("http://meusite.com");
  });
  it("localhost sem proxy fica em http", () => {
    const h = new Headers({ host: "localhost:3000" });
    expect(publicOrigin(h)).toBe("http://localhost:3000");
  });
});
