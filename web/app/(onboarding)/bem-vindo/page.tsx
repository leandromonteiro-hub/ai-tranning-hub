import { redirect } from "next/navigation";
import { getSession } from "@/lib/session";
import { OnboardingWizard } from "@/components/onboarding/OnboardingWizard";

export default async function BemVindoPage() {
  const session = await getSession();
  if (!session) redirect("/login");
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <OnboardingWizard />
    </div>
  );
}
