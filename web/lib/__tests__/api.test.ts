import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../api";

describe("apiFetch", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("chama o proxy com o path limpo", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await apiFetch("/athletes/me");
    expect(fetchMock).toHaveBeenCalledWith("/api/proxy/athletes/me", undefined);
  });
});
