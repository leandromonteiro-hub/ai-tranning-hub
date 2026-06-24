import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { resolveApiUrl } from "@/lib/config";
import { AppShell } from "@/components/AppShell";

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await getSession();
  if (!session) redirect("/login");

  let userName = "";
  try {
    const res = await fetch(resolveApiUrl("athletes/me"), {
      headers: { Authorization: `Bearer ${session.token}` },
      cache: "no-store",
    });
    if (res.ok) userName = (await res.json()).full_name ?? "";
  } catch {
    // backend indisponível — segue com nome vazio; middleware já garantiu o cookie
  }

  return (
    <AppShell role={session.role} userName={userName}>
      {children}
    </AppShell>
  );
}
