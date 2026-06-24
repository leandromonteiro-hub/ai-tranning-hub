import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { ComingSoon } from "@/components/ComingSoon";

export default async function AdminPage() {
  const session = await getSession();
  if (session?.role !== "ADMIN") redirect("/");
  return <ComingSoon title="📋 Painel do treinador" milestone="M5" />;
}
