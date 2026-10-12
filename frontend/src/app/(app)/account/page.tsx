import type { Metadata } from "next";
import { Suspense } from "react";
import { AccountView } from "@/components/account/AccountView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Account" };

export default function AccountPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-3xl" />}>
      <AccountContent />
    </Suspense>
  );
}

async function AccountContent() {
  const result = await attempt(api.me);
  if (!result.ok) return <ServerError error={result.error} />;
  return <AccountView user={result.data} />;
}
