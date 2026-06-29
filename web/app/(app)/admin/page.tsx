import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { AdminView } from "@/components/admin/AdminView";

export default async function AdminPage() {
  const session = await getSession();
  if (session?.role !== "ADMIN") redirect("/");
  return <AdminView />;
}
