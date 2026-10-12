import type { Metadata } from "next";
import { Suspense } from "react";
import { MembersView } from "@/components/members/MembersView";
import { Skeleton } from "@/components/ui/Panel";
import { ServerError } from "@/components/ui/ServerError";
import { api, attempt } from "@/lib/api";

export const metadata: Metadata = { title: "Members" };

export default function MembersPage() {
  return (
    <Suspense fallback={<Skeleton className="mx-auto h-96 max-w-4xl" />}>
      <MembersContent />
    </Suspense>
  );
}

async function MembersContent() {
  const result = await attempt(async () => api.members((await api.franchise()).league.id));
  if (!result.ok) return <ServerError error={result.error} />;
  return <MembersView initial={result.data} />;
}
