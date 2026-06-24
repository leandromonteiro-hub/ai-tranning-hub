"use client";

import { SWRConfig } from "swr";
import type { ReactNode } from "react";
import { jsonFetcher } from "@/lib/api";

export function SWRProvider({ children }: { children: ReactNode }) {
  return (
    <SWRConfig value={{ fetcher: jsonFetcher, revalidateOnFocus: false }}>{children}</SWRConfig>
  );
}
